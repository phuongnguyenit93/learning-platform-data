# `@AuthenticationPrincipal Jwt` and Accessing Claims in Controllers

## 1. Goal: Obtaining the Verified Identity Instead of Manually Decoding Bearer Tokens

In a **Spring Boot + Spring Security OAuth 2.0 Resource Server** application, clients call the API using an **OAuth 2.0 access token**:

~~~http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

If the access token is a signed JWT, Spring Security can automatically validate the token and build an authentication object before the request reaches the controller. The controller only needs to declare:

~~~java
@GetMapping("/api/me")
public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of("subject", jwt.getSubject());
}
~~~

There is no need to manually read the `Authorization` header, strip the `Bearer ` prefix, Base64URL-decode the payload, or verify the JWT signature in the controller.

**`@AuthenticationPrincipal Jwt`** is the way to inject the **JWT principal already verified by Spring Security Resource Server** into a Spring MVC controller parameter. From `Jwt`, the application can access claims such as `sub`, `iss`, `aud`, `scope`, and custom claims.

It is important to distinguish three groups of responsibilities:

1. **Authentication**: Spring Security verifies the access token and creates the principal.
2. **Reading identity and claims**: the controller/service reads verified information via `Jwt` or `Authentication`.
3. **Authorization**: checking whether the principal is allowed to perform an action or access a specific record.

Being able to read a claim like `tenant_id` does not automatically prove the caller is allowed to view every record in that tenant. And a custom claim should only be trusted within the context of fully configured **issuer, audience, JWT validation, and token contract**.

## 2. What Is the `Jwt` Object Here?

### 2.1. JWT Access Token and Spring `Jwt`

A JWT access token may contain claims such as:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read profile",
  "client_id": "shop-web",
  "tenant_id": "tenant-42",
  "preferred_username": "phuong",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

This JSON illustrates a **payload**, not a genuinely signed token; the timestamps are purely illustrative.

When the Resource Server authenticates successfully, `org.springframework.security.oauth2.jwt.Jwt` is a Java object containing:

- **Token value**: the raw access token string.
- **Headers**: JOSE/JWS headers such as `alg`, `kid`, `typ`.
- **Claims**: claim names and values read by the decoder from the JWT.
- **Convenient accessors**: `getSubject()`, `getIssuer()`, `getAudience()`, `getExpiresAt()`, `getIssuedAt()`, `getClaimAsString(...)`, and more.

The `Jwt` object is **not the same** as `java.security.Principal` in the sense of that simple Java interface; it is used by Spring Security as the **principal inside `Authentication`** for the JWT Resource Server case.

### 2.2. Relationship Between `JwtAuthenticationToken` and `Jwt`

In the standard JWT Resource Server flow, Spring Security creates a **`JwtAuthenticationToken`**. This object implements Spring Security's `Authentication` model.

~~~text
SecurityContext
    |
    v
Authentication = JwtAuthenticationToken
    |
    +-- principal = Jwt
    |
    +-- name = sub in typical configuration
    |
    +-- authorities = [SCOPE_orders.read, SCOPE_profile, ...]
    |
    +-- authenticated = true
~~~

For example:

~~~java
@GetMapping("/api/security-info")
public Map<String, Object> securityInfo(Authentication authentication) {
    Object principal = authentication.getPrincipal();

    return Map.of(
        "authenticationType",
        authentication.getClass().getSimpleName(),
        "principalType",
        principal.getClass().getSimpleName(),
        "name",
        authentication.getName()
    );
}
~~~

For instance, this can return names such as `JwtAuthenticationToken`, `Jwt`, and `user-123` when the request is authenticated via JWT.

**Do not confuse them**:

- `Jwt`: holds the token/claims data after decoding and validation.
- `JwtAuthenticationToken`: describes an **`Authentication`** built from a JWT, carrying authorities and principal.
- `Authentication#getName()`: the principal name chosen by Spring Security; by default usually based on `sub`, though customizable.
- `@AuthenticationPrincipal`: retrieves **`authentication.getPrincipal()`**, not the entire `Authentication` object.

### 2.3. Flow from Bearer Token to Controller Parameter

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["FilterChainProxy / SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["JwtAuthenticationProvider"]
    D --> E["JwtDecoder verifies JWS and JWT validators"]
    E --> F{"Token valid?"}
    F -->|No| G["Authentication failure / typically 401"]
    F -->|Yes| H["JwtAuthenticationConverter"]
    H --> I["JwtAuthenticationToken"]
    I --> J["SecurityContextHolder"]
    J --> K["AuthorizationFilter checks authorities"]
    K --> L{"Access allowed?"}
    L -->|No| M["Typically 403"]
    L -->|Yes| N["Spring MVC Controller"]
    N --> O["@AuthenticationPrincipal Jwt"]
    O --> P["Read claims and execute business logic"]
~~~

This diagram is simplified; an application also includes other filters such as CORS, CSRF, anonymous authentication, and exception handling. **The controller is only invoked after the request passes the applicable filters and policies.**

Resolving `Authentication` into the `@AuthenticationPrincipal` parameter is handled by Spring MVC's argument resolution integration with Spring Security (for example `AuthenticationPrincipalArgumentResolver`), not by Spring re-decoding the token on every method call.

## 3. Setting Up a JWT Resource Server to Use `@AuthenticationPrincipal Jwt`

### 3.1. Dependencies

Gradle example with Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Use compatible Spring Boot/Spring Security versions in your project. This path is for the **Servlet stack**; WebFlux uses reactive security APIs and configuration.

### 3.2. Configuring Issuer and Audience

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

These addresses and audience names are examples. `issuer-uri` must match the actual `iss` of the access token; `audiences` binds the token to the API in Spring Boot versions that support this property.

An access token validly signed by the right issuer but carrying `aud = billing-api` is not an access token meant for Orders API. Checking signature/issuer while skipping audience can lead to **cross-service token confusion**.

### 3.3. `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

To ensure an example like `GET /api/orders` matches the rule under any path matcher setup, you can include both `"/api/orders"` and `"/api/orders/**"`. In this guide, `/api/me` is protected by `anyRequest().authenticated()`.

When the chain receives a valid JWT, Spring Security creates a `Jwt` principal. If the JWT has an invalid signature, is expired, or fails issuer or audience validators, the request typically receives **401 Unauthorized** before the controller runs. When the token is valid but lacks `SCOPE_orders.read` for an endpoint requiring that permission, it typically receives **403 Forbidden**.

**Important note:** The example does not explicitly disable CSRF because the article does not require it. When designing a purely stateless API using only Bearer headers and no cookie-based authentication, evaluate CSRF settings according to your threat model. Do not disable CSRF indiscriminately just to make a POST example work.

## 4. Accessing Common Claims with Dedicated Accessors

A controller can retrieve standard values from `Jwt`:

~~~java
package com.example.orders.api;

import java.time.Instant;
import java.net.URL;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public IdentityResponse me(@AuthenticationPrincipal Jwt jwt) {
        return new IdentityResponse(
            jwt.getSubject(),
            jwt.getIssuer() == null ? null : jwt.getIssuer().toString(),
            jwt.getAudience(),
            jwt.getIssuedAt(),
            jwt.getExpiresAt()
        );
    }

    public record IdentityResponse(
        String subject,
        String issuer,
        List<String> audiences,
        Instant issuedAt,
        Instant expiresAt
    ) {}
}
~~~

Does `Jwt#getIssuer()` return `java.net.URL` in some descriptions? **In Spring Security's API, `Jwt#getIssuer()` returns `java.net.URL` or `java.net.URI` depending on the version; the snippet only calls `toString()`**, so it does not depend on the exact return type in the controller response. You can omit importing `URL` in the example if your IDE marks it unused.

Key accessors:

| `Jwt` Accessor | Claim | Typical Java Type | Meaning |
|---|---|---|---|
| `getSubject()` | `sub` | `String` | Token subject |
| `getIssuer()` | `iss` | `URL` | Converted issuer |
| `getAudience()` | `aud` | `List<String>` | Target audiences of the token |
| `getExpiresAt()` | `exp` | `Instant` | Expiration timestamp |
| `getNotBefore()` | `nbf` | `Instant` | Not-before timestamp |
| `getIssuedAt()` | `iat` | `Instant` | Issued-at timestamp |
| `getId()` | `jti` | `String` | JWT ID if present |
| `getClaimAsString("client_id")` | `client_id` | `String` or `null` | OAuth 2.0 client ID per contract |

`Jwt` also provides `getClaims()` to obtain a map of claim names to values, `getClaim(String)` to read an individual claim, and typed conversion accessors (`getClaimAsStringList`, `getClaimAsInstant`, etc.).

**Type note:** after `JwtDecoder`, standard claims may be **normalized into Java types** by Spring Security. `exp`/`iat` are typically `Instant`; `aud` may be normalized into a list of Strings. Do not expect raw JSON types to remain unchanged in every case.

### 4.1. Return Only the Data the API Actually Needs

The example above returns metadata to demonstrate accessing claims. In production, **avoid creating arbitrary endpoints that return all JWT claims**, because the JWS payload may contain user details, tenant info, or internal metadata.

A safer trimmed profile response:

~~~java
@GetMapping("/api/profile")
public ProfileResponse profile(@AuthenticationPrincipal Jwt jwt) {
    return new ProfileResponse(
        jwt.getSubject(),
        jwt.getClaimAsString("preferred_username")
    );
}

public record ProfileResponse(
    String id,
    String displayName
) {}
~~~

A profile endpoint may display `preferred_username`, yet when performing authorization checks or data lookups, **do not rely on a display name as an immutable identifier**.

## 5. Claim Names and Types: Distinctions to Keep in Mind

### 5.1. `getClaim(...)` vs. `getClaimAsString(...)`

Suppose the issuer emits custom claims:

~~~json
{
  "tenant_id": "tenant-42",
  "account_tier": "enterprise",
  "feature_flags": ["orders-search", "exports"],
  "login_count": 12
}
~~~

You can read them:

~~~java
Object rawTenant = jwt.getClaim("tenant_id");
String tenant = jwt.getClaimAsString("tenant_id");
List<String> features = jwt.getClaimAsStringList("feature_flags");
~~~

The `getClaimAs...` helpers are convenient when the claim contract is defined and the decoder has normalized the types appropriately. However, when a claim **determines data scope or access permissions**, do not rely on implicit type coercion to patch over a token violating the contract.

Dangerous example:

~~~java
// Do not use for security claims requiring a strict type contract:
String tenant = String.valueOf(jwt.getClaim("tenant_id"));
~~~

If the issuer sends `tenant_id: 42` or `tenant_id: null`, `String.valueOf(...)` produces `"42"` or `"null"`, accidentally passing through business logic that expected a genuine String.

### 5.2. Safely Reading a Custom Claim Required to Be a String

If the contract requires `tenant_id` to be a non-blank String, you can write a helper:

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.jwt.Jwt;

public final class JwtClaims {

    private JwtClaims() {}

    public static String requiredTenantId(Jwt jwt) {
        Object value = jwt.getClaims().get("tenant_id");

        if (value instanceof String tenantId && !tenantId.isBlank()) {
            return tenantId;
        }

        throw new IllegalStateException(
            "A validated access token must have tenant_id");
    }
}
~~~

**Context condition:** the helper should only be called **after authentication**. For required claims used to make authorization decisions, a better option is **a validator in `JwtDecoder` that rejects missing/malformed tokens before the controller runs**. That way, the controller does not have to decide authentication errors itself.

If the helper above throws `IllegalStateException` inside a controller, the response may become **500** if unhandled. Thus, the snippet illustrates **type-safe access and invariants**, not complete production error handling. A later section shows validating `tenant_id` directly during JWT validation.

### 5.3. Reading List Claims

Suppose the claims contain:

~~~json
{
  "groups": ["support", "orders-team"],
  "roles": ["ORDER_READER", "ORDER_EDITOR"]
}
~~~

To ensure a claim is genuinely a collection of Strings per contract:

~~~java
public static List<String> roles(Jwt jwt) {
    Object raw = jwt.getClaims().get("roles");

    if (raw == null) {
        return List.of(); // Valid only if roles is optional in the contract.
    }

    if (!(raw instanceof List<?> values)) {
        throw new IllegalArgumentException(
            "roles must be a JSON array");
    }

    for (Object value : values) {
        if (!(value instanceof String role) || role.isBlank()) {
            throw new IllegalArgumentException(
                "roles must contain non-empty strings");
        }
    }

    return values.stream()
        .map(String.class::cast)
        .toList();
}
~~~

Import `java.util.List`. If the contract treats `roles` as a **security claim**, move this validation into a controlled validator or converter before granting `Authentication`/authorities. The code here clarifies distinguishing a **String array** from a **single String, mixed array, or Number**.

Do not automatically treat `"ROLE_ADMIN"` in a custom claim as a valid permission simply because the token's signature is valid. The issuer and API must agree on role semantics, role names, and how they map to Spring authorities.

### 5.4. Missing, Null, Empty, and Wrongly Typed Claims

Consider the custom claim `tenant_id`:

| Payload | What Happens | Handling for a Required Contract |
|---|---|---|
| `tenant_id` absent | `jwt.getClaim("tenant_id")` is typically `null` | Reject token |
| `"tenant_id": null` | Null value / may be omitted by converter | Reject token |
| `"tenant_id": ""` | Empty String | Reject token |
| `"tenant_id": 42` | Number | Reject token |
| `"tenant_id": ["tenant-42"]` | Array | Reject token |
| `"tenant_id": "tenant-42"` | Non-empty String | Valid subject to other checks |

For **non-security claims**, such as `locale` for language formatting, a fallback can be acceptable:

~~~java
public static String localeForDisplay(Jwt jwt) {
    Object raw = jwt.getClaims().get("locale");

    if (raw instanceof String locale) {
        return switch (locale) {
            case "vi-VN", "en-US" -> locale;
            default -> "vi-VN";
        };
    }

    return "vi-VN";
}
~~~

The rule is that **fallbacks must never grant extra permissions**. Never substitute a missing tenant with `"global"`, substitute a missing subject with an email, or inject default scopes.

## 6. How Is `@AuthenticationPrincipal` Resolved?

### 6.1. Spring MVC Argument Resolution

When a controller declares:

~~~java
@GetMapping("/api/me")
public String me(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

Spring Security integrates with Spring MVC through an **argument resolver**. Conceptually, the resolver fetches:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

Object principal = authentication == null
    ? null
    : authentication.getPrincipal();
~~~

And then attempts to supply the principal to the parameter of type `Jwt`.

This injection **does not fetch a new token from the issuer**, does not call JWKS again, and does not perform separate JWT validation inside the controller. Authentication has already been handled by upstream security filters.

### 6.2. What If the Request Has No Principal Yet?

On a `permitAll` endpoint, a request may arrive without a Bearer token. In that case:

- `Authentication` may be an anonymous authentication or absent depending on configuration.
- Principal may not be a `Jwt` (for example, an anonymous principal is a String).
- `@AuthenticationPrincipal Jwt` may receive `null` when the principal type does not match and the default attribute does not force an immediate error.

Example of a public endpoint that responds differently depending on whether a JWT is present:

~~~java
@GetMapping("/api/public/greeting")
public Map<String, String> greeting(
        @AuthenticationPrincipal Jwt jwt) {

    if (jwt == null) {
        return Map.of("message", "Hello, guest");
    }

    return Map.of("message", "Hello, " + jwt.getSubject());
}
~~~

This example illustrates a **nullable parameter** on a public endpoint. Never apply “if `jwt` is null treat as guest and still expose private data” logic to endpoints requiring authentication.

**Subtle point:** `permitAll` does not automatically bypass `BearerTokenAuthenticationFilter`. If a request hits a public endpoint while sending an invalid Bearer token, the filter may still return **401** before the controller runs. Only requests without a token proceed per the `permitAll` policy.

### 6.3. `errorOnInvalidType`

The annotation supports throwing an error when the principal has an incompatible type:

~~~java
@GetMapping("/api/strict-profile")
public String strictProfile(
        @AuthenticationPrincipal(errorOnInvalidType = true) Jwt jwt) {
    return jwt.getSubject();
}
~~~

When a principal exists but is not a `Jwt`, instead of passing `null` due to type mismatch, the resolver can throw an exception (such as `ClassCastException`). This attribute is **not an authentication mechanism** and does not replace `authenticated()`/scope policies in the filter chain.

Normally, ensure protected APIs enforce the proper JWT mechanism and write explicit code rather than expecting `errorOnInvalidType` to act as a security gate.

### 6.4. SpEL `expression` on the Annotation

`@AuthenticationPrincipal` supports SpEL to extract a property of the principal.

Example when only the subject is needed:

~~~java
@GetMapping("/api/subject")
public Map<String, String> subject(
        @AuthenticationPrincipal(expression = "subject") String subject) {

    return Map.of("subject", subject);
}
~~~

Or extracting a custom claim from `Jwt`:

~~~java
@GetMapping("/api/tenant-label")
public Map<String, String> tenantLabel(
        @AuthenticationPrincipal(
            expression = "claims['tenant_id']"
        ) String tenantId) {

    return Map.of("tenant", tenantId);
}
~~~

Expressions run against the **principal** retrieved from `Authentication`. On `Jwt`, the `subject` property maps to `getSubject()`, while `claims['tenant_id']` looks up in the claims map.

**Notes when using expressions:**

- A missing claim or a non-`Jwt` principal can yield null or make the expression inapplicable.
- `Map.of(...)` rejects nulls; the example is only safe when `sub`/`tenant_id` are guaranteed by validators and the endpoint is protected.
- For complex business logic, **injecting the full `Jwt` and checking typed claims in a service** is usually clearer than long SpEL expressions in annotations.
- Never use expressions to grant scopes or bypass validators.

For example, `@AuthenticationPrincipal(expression = "claims['tenant_id']")` only **reads the claim**; it does not prove the token is valid for that tenant or verify tenant ownership of the record.

## 7. Use `Authentication` When You Need Authorities Rather Than Only Claims

A controller can accept `Authentication` directly:

~~~java
@GetMapping("/api/access")
public AccessInfo access(Authentication authentication) {
    return new AccessInfo(
        authentication.getName(),
        authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList()
    );
}

public record AccessInfo(String name, List<String> authorities) {}
~~~

Imports:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
~~~

This snippet demonstrates reading **authorities already attached to `Authentication` by Spring Security**, rather than reading raw `scope` and inferring permissions yourself.

### 7.1. Claims and Authorities Are Different

Example JWT:

~~~json
{
  "scope": "orders.read orders.write",
  "roles": ["ORDER_ADMIN"]
}
~~~

In a standard JWT Resource Server setup, scopes may become:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

The `roles` claim **does not automatically** become `ROLE_ORDER_ADMIN`. To map custom roles, the application must configure a converter and an appropriate trust/allowlist policy.

Protecting an endpoint with:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

is safer than manually writing in a controller:

~~~java
// Discouraged as the primary endpoint protection layer:
if (jwt.getClaimAsString("scope").contains("orders.read")) {
    // ...
}
~~~

Because substring matching with `contains` can produce false positives (such as `orders.read.all`), diverges from authority mapping, and easily misses malformed token schemas.

### 7.2. `Authentication#getName()` Is Not Always `sub`

`JwtAuthenticationConverter` can configure which claim is used as the principal name, such as `preferred_username` instead of `sub`. In that case:

~~~java
authentication.getName()
~~~

may differ from:

~~~java
jwt.getSubject()
~~~

If the database identity key must be `sub`, document that explicitly in the contract and use `jwt.getSubject()` or an identity abstraction properly scoped by issuer. Do not assume `preferred_username` is immutable.

### 7.3. When Should You Use `@AuthenticationPrincipal Jwt`?

| Controller Goal | Suitable Parameter |
|---|---|
| Reading `sub`, `iss`, `tenant_id` from a JWT | `@AuthenticationPrincipal Jwt` |
| Reading `Authentication` name and authorities | `Authentication` |
| Reading subject directly in a short method | `@AuthenticationPrincipal(expression = "subject") String` |
| OIDC login/session endpoint where principal is an OIDC user | `@AuthenticationPrincipal OidcUser` |
| Resource Server accepting opaque tokens | `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` or `Authentication` |
| Business layer should not depend directly on Spring Security | Pass an identity DTO/context safely constructed from the principal |

Do not force an application using multiple authentication mechanisms to produce the same `Jwt` parameter everywhere. Choose the appropriate abstraction for each security chain.

## 8. JWT Resource Server Differs from OIDC Login and Opaque Tokens

### 8.1. JWT Resource Server

With:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

you typically get:

~~~text
Authentication: JwtAuthenticationToken
Principal:      Jwt
~~~

This is the primary case for `@AuthenticationPrincipal Jwt`.

### 8.2. OIDC Login

When the application acts as an **OIDC Client** using:

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

the principal is usually an **`OidcUser`** (such as `DefaultOidcUser`), not a `Jwt` directly. A controller can use:

~~~java
@GetMapping("/web/me")
public String webMe(
        @AuthenticationPrincipal OidcUser oidcUser) {

    return oidcUser.getSubject();
}
~~~

Import `org.springframework.security.oauth2.core.oidc.user.OidcUser`.

An `OidcUser` may contain an ID Token and UserInfo, yet **an OIDC ID Token is not an OAuth 2.0 access token for calling a Resource Server API**. Never design API endpoints that accept ID Tokens as Bearer tokens merely to obtain login-style identity claims.

### 8.3. Opaque Access Tokens

If an API configures:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
);
~~~

Spring Security uses token introspection instead of JWT decoding. The typical principal implements **`OAuth2AuthenticatedPrincipal`**, not `Jwt`.

You can declare:

~~~java
@GetMapping("/api/opaque-me")
public Map<String, String> opaqueMe(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    return Map.of(
        "name",
        principal.getName()
    );
}
~~~

Import `org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal`.

Introspection attributes and types depend on the Authorization Server; do not mechanically apply `Jwt#getSubject()` or `getAudience()` assumptions onto an opaque principal.

### 8.4. Multiple `SecurityFilterChain`s

If the same application has a `/api/**` chain using JWTs and a `/web/**` chain using OIDC login/sessions, the principal type can vary per request. `FilterChainProxy` selects a chain based on `securityMatcher` and `@Order`; **never** write a controller assuming every request has a `Jwt` if the endpoint could be reached through multiple authentication types.

Separating endpoints and service identity models prevents type mismatch errors.

## 9. Validating Claims Before the Controller: Token Errors Belong to Authentication

### 9.1. Why Not Only Check `tenant_id` in the Controller?

Suppose Orders API is multi-tenant and every access token targeting the API must contain:

~~~json
{
  "tenant_id": "tenant-42"
}
~~~

If you only read:

~~~java
String tenant = jwt.getClaimAsString("tenant_id");
~~~

and allow a null tenant to fall back to a shared tenant, the application could accidentally cross tenant boundaries. If code throws a generic exception when the claim is missing, an HTTP 500 may occur after the request was already authenticated.

A **contract-required claim for identification or data partitioning** should be enforced in an **`OAuth2TokenValidator<Jwt>`** to reject invalid tokens **before the controller executes**.

### 9.2. Validator Requiring `tenant_id`

Example manually configuring a decoder with a trusted issuer and JWKS URI:

~~~java
package com.example.orders.security;

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
public class JwtContractConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return invalid("Access token audience is not orders-api");
        };

        OAuth2TokenValidator<Jwt> tenantValidator = jwt -> {
            Object raw = jwt.getClaims().get("tenant_id");
            if (raw instanceof String tenantId && !tenantId.isBlank()) {
                return OAuth2TokenValidatorResult.success();
            }
            return invalid("Missing or invalid tenant_id");
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard,
                audienceValidator,
                tenantValidator
            )
        );

        return decoder;
    }

    private static OAuth2TokenValidatorResult invalid(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null)
        );
    }
}
~~~

This snippet uses `NimbusJwtDecoder.withJwkSetUri(...)`, so it explicitly keeps **`JwtValidators.createDefaultWithIssuer(ISSUER)`** alongside the audience and tenant validators. If the application previously relied on Spring Boot auto-configuration properties for the decoder, defining a custom bean can cause auto-configuration to **back off**; in that case, do not assume the `audiences` property or prior validation still applies automatically.

**Note on raw JSON types:** `OAuth2TokenValidator<Jwt>` receives claims after the decoder may have normalized types. For a custom `tenant_id`, it normally still reflects String/Number/Array, yet if the contract requires strict checks on raw JSON types of registered claims, review the conversion/parser behavior accordingly. Never use generic casting to salvage schema-invalid tokens.

### 9.3. HTTP Status When a Validator Fails

If `tenant_id` is a required claim in the token contract, a token with a missing or invalid claim must be rejected during **authentication**, typically producing:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

If the token is valid but lacks the endpoint's required authority, `AuthorizationFilter` rejects it and typically returns:

~~~http
HTTP/1.1 403 Forbidden
~~~

Do not return 403 for a token that failed the authentication contract and was caught manually inside a controller. 403 is appropriate for **authenticated but lacking permission**.

## 10. Using `Jwt` Safely in a Multi-Tenant API

### 10.1. Claims Provide Identity Context, Not Resource Permissions

Suppose a JWT contains:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

And the request is:

~~~http
GET /api/orders/9001 HTTP/1.1
Authorization: Bearer <VALID_ACCESS_TOKEN>
~~~

The endpoint requires `SCOPE_orders.read`. However, holding this scope only indicates the caller is allowed to read orders under the **general API policy**.

If order 9001 belongs to `tenant-99`, a user from `tenant-42` must not view it unless the system has an explicitly designed cross-tenant policy.

### 10.2. Tenant-Scoped Controller + Service Pattern

~~~java
package com.example.orders.api;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    private final OrdersService ordersService;

    public OrdersController(OrdersService ordersService) {
        this.ordersService = ordersService;
    }

    @GetMapping("/{orderId}")
    public OrderResponse order(
            @PathVariable long orderId,
            @AuthenticationPrincipal Jwt jwt) {

        // Validator guarantees tenant_id at the decoder.
        String tenantId =
            (String) jwt.getClaims().get("tenant_id");

        String subject = jwt.getSubject();

        return ordersService.findOrderForCaller(
            orderId, tenantId, subject
        );
    }
}
~~~

Illustrative service:

~~~java
public OrderResponse findOrderForCaller(
        long orderId,
        String tenantId,
        String subject) {

    Order order = repository.findByIdAndTenantId(orderId, tenantId)
        .orElseThrow(() ->
            new ResponseStatusException(HttpStatus.NOT_FOUND));

    // If the contract requires per-user permissions,
    // check owner/ACL here rather than relying on scope alone.
    if (!permissionService.canRead(subject, order)) {
        throw new ResponseStatusException(HttpStatus.FORBIDDEN);
    }

    return orderMapper.toResponse(order);
}
~~~

`OrdersService`, `OrderResponse`, `Order`, `repository`, `permissionService`, and `orderMapper` are illustrative domain components to be implemented against actual data. The controller assumes `JwtDecoder` already validated `tenant_id` as a non-blank String and `sub` per contract; without those validators, handle null/invalid types before calling the service.

**Key point:** the repository queries by **both order ID and tenant ID**. Never fetch an arbitrary order by ID and decide afterward solely using a user display name from the JWT. Querying by tenant (plus owner/ACL checks) reduces the risk of data leakage through guessable IDs.

### 10.3. Is `subject` Always a Human User?

Not necessarily. With an **Authorization Code** token, `sub` usually represents a user. With a **Client Credentials** access token, `sub` may represent a **client/service** depending on the issuer's profile.

Therefore, classify the principal type according to the grant/token profile and API contract. Do not blindly treat every `sub` as a user ID or query the users table for a machine principal if the API accepts machine-to-machine tokens.

When forming an identity key, combining **issuer + subject** may be necessary to prevent subject collisions across multiple issuers. In a single-issuer API, the subject can be scoped under the verified issuer; in multi-issuer setups, maintain that boundary strictly.

## 11. Should You Pass `Jwt` Down Through Every Service Layer?

### 11.1. Quick Approach: Controller Uses `Jwt`

In a small application, a controller can do:

~~~java
@GetMapping("/api/me")
public String subject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

This is concise for displaying or using a couple of simple claims, provided validation rules and claim types are already guaranteed.

### 11.2. Sustainable Approach: Convert to an Identity Abstraction

In larger business applications, passing raw `Jwt` objects across services and repositories creates **coupling** to Spring Security and the issuer's token structure.

You can define a small type containing only the required fields:

~~~java
package com.example.orders.identity;

public record CallerIdentity(
    String issuer,
    String subject,
    String tenantId
) {}
~~~

Factory:

~~~java
package com.example.orders.identity;

import org.springframework.security.oauth2.jwt.Jwt;

public final class CallerIdentityFactory {

    private CallerIdentityFactory() {}

    public static CallerIdentity fromValidatedJwt(Jwt jwt) {
        // Contract validators guarantee iss, sub, tenant_id.
        return new CallerIdentity(
            jwt.getIssuer().toString(),
            jwt.getSubject(),
            (String) jwt.getClaims().get("tenant_id")
        );
    }
}
~~~

Controller:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> myOrders(
        @AuthenticationPrincipal Jwt jwt) {

    CallerIdentity caller =
        CallerIdentityFactory.fromValidatedJwt(jwt);

    return ordersService.findOrdersForCaller(caller);
}
~~~

Benefits:

- Services do not parse JWTs themselves.
- When the provider renames a custom claim, changes stay localized in the adapter/factory.
- Service unit tests can use an identity DTO instead of JWT tokens.
- It is easier to distinguish `subject`, `tenantId`, and issuer than passing an untyped `Map<String, Object>`.

Still, an identity abstraction **does not grant permissions by itself**. Services and controllers must continue enforcing scope/authority checks and object-level authorization policies.

### 11.3. Avoid Using `SecurityContextHolder` Everywhere

You can read:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

However, if services repeatedly pull from global/thread-local context, code becomes harder to test and prone to bugs under async processing. Passing an explicit `CallerIdentity` from the authenticated boundary into services is usually cleaner.

Never store `Authentication` or `Jwt` in static mutable fields, global caches for “current user”, or use them beyond the request lifecycle without safe context propagation.

## 12. Handling Anonymous/Null Principals and Returning Proper HTTP Responses

### 12.1. Protected Endpoints

If `GET /api/me` requires `authenticated()` and the API only accepts JWT Bearer tokens, requests without a token or with an invalid token are typically rejected by Spring Security **before the controller runs**.

~~~http
GET /api/me HTTP/1.1
~~~

Typically receives:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Thus, code like:

~~~java
@GetMapping("/api/me")
public String me(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

relies on the assumption that `SecurityFilterChain` protects the endpoint and no other authentication mechanism creates a different principal type. When custom chains, multiple auth mechanisms, or public endpoints exist, explicitly handle type and nullability.

### 12.2. Public Endpoints That Vary Output Based on Token Presence

On a `permitAll` endpoint:

~~~java
@GetMapping("/api/public/welcome")
public String welcome(@AuthenticationPrincipal Jwt jwt) {
    return jwt == null
        ? "Welcome, guest"
        : "Welcome, " + jwt.getSubject();
}
~~~

This is presentation logic. Never use this pattern to allow anonymous callers to view private data.

**Note:** A Bearer token *that is present yet invalid* can still trigger 401 before the controller, even on a `permitAll` endpoint.

### 12.3. Where Should Missing Required Claims Be Handled?

| Issue | Appropriate Layer | Typical HTTP Status |
|---|---|---|
| No token on a protected endpoint | Security filters / entry point | 401 |
| Invalid signature/expired/wrong issuer/audience | `JwtDecoder` / validator | 401 |
| Missing required custom claim in token contract | `OAuth2TokenValidator<Jwt>` | 401 |
| Valid token missing `SCOPE_orders.read` | Authorization rules | 403 |
| Valid token, sufficient scope, but forbidden for specific order | Service/ownership policy | 403 or 404 |
| Missing optional UI claim like `locale` | Controller/presentation | Safe fallback |
| Non-`Jwt` principal from hitting the wrong auth chain | Review security architecture | Fix config/guards appropriately |

Never let a missing required claim reach the controller only to return 200 with empty data or a global default. Conversely, do not turn every optional display claim into a requirement for JWT validity.

## 13. `@AuthenticationPrincipal` and Method Security

Endpoints commonly use `authorizeHttpRequests` to enforce scopes before the controller runs:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

Additionally, services can use method security once enabled:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {}
~~~

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderResponse loadOrder(long orderId, CallerIdentity caller) {
    return findOrderForCaller(orderId, caller.tenantId(), caller.subject());
}
~~~

Imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
~~~

**Remember that `@AuthenticationPrincipal Jwt` only supplies the principal, not an authorization rule.** Method security and URL security must use appropriate authorities and policies. If tenant/owner checks are needed, enforce them in the service or a well-designed authorization manager.

Never pull raw `scope` from the JWT and use `String.contains(...)` for authorization decisions. Spring Security already provides authority mapping and `hasAuthority(...)`, avoiding substring bugs or inconsistent token schemas.

## 14. Testing Controllers That Use `@AuthenticationPrincipal Jwt`

### 14.1. Two Distinct Testing Levels

There are at least two scopes:

1. **Controller/authorization testing**: creates a mock `Jwt` principal to verify injection and responses.
2. **Full JWT Resource Server testing**: sends a real Bearer header through the filter chain, exercising the decoder, issuer, JWKS, audience, and claims.

Spring Security Test provides the `jwt()` helper to mock JWT authentication in MockMvc. It is very useful for (1) but **does not prove that JWT signature, issuer, JWKS fetching, and audience validators actually run**.

### 14.2. MockMvc Example with a Mock JWT

Test dependency:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
~~~

Example test method:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void returnsPrincipalSubject() throws Exception {
    mvc.perform(get("/api/me").with(jwt().jwt(token -> token
            .subject("user-123")
            .claim("tenant_id", "tenant-42")
        )))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("user-123"));
}
~~~

The example assumes `mvc` is a configured `MockMvc` field and `/api/me` returns JSON containing `subject` as in the earlier controller. In real code, static imports can be written on a single line if required by your style checker.

### 14.3. Testing Scopes/Authorities

If an endpoint requires `SCOPE_orders.read`:

~~~java
mvc.perform(get("/api/orders/42").with(
    jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")
    )
));
~~~

Import:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

This test simulates a caller holding the authority. It does not verify whether an access token with a `scope` claim is actually mapped to that authority by your converter.

To test the **converter**, unit-test `JwtAuthenticationConverter`. To test **JWT validation**, test the decoder using test JWTs signed with test keys and a controlled JWKS source or matching integration tests.

### 14.4. Recommended Test Cases

| Scenario | Expected Outcome |
|---|---|
| `/api/me` with valid JWT | `Jwt` principal injected, subject returned |
| No token on protected endpoint | 401 before controller |
| Invalid signature or expired token | 401 before controller |
| Wrong-audience token | 401 when audience validator is configured |
| JWT missing required `tenant_id` | 401 at validator, never reaches service |
| JWT with Number `tenant_id` instead of String | Rejected per contract |
| Valid JWT missing scope for order endpoint | 403 |
| Valid JWT with right scope but different tenant | 403/404 per business policy |
| Public endpoint without JWT | Nullable `Jwt`, guest response |
| Opaque token at endpoint expecting `Jwt` | Redesign principal type, do not cast |

If you only use `@WithMockUser`, the principal is typically `UserDetails`/String depending on test setup, not `Jwt`. For controllers expecting `@AuthenticationPrincipal Jwt`, use appropriate mock JWT authentication.

## 15. Common Mistakes

### 15.1. Manually Decoding JWTs in a Controller

~~~java
String token = request.getHeader("Authorization");
String payload = new String(
    Base64.getUrlDecoder().decode(token.split("\\.")[1])
);
~~~

**Unsafe for authentication**: JWS Base64URL payloads are not encrypted; reading the JSON does not verify signature, issuer, or audience. Moreover, the snippet mishandles the `Bearer ` scheme and malformed tokens.

Let the Resource Server's `JwtDecoder` validate the token, then accept `@AuthenticationPrincipal Jwt`.

### 15.2. Using `getClaimAsString` Everywhere Regardless of Contract

Claims may be Strings, Booleans, Numbers, Collections, or Objects. For security claims, validate exact types per contract, avoid arbitrary coercion, and never provide defaults that widen permissions.

### 15.3. Using `jwt.getTokenValue()` for Display or Logging

`getTokenValue()` returns the **actual access token**. It is a bearer credential; anyone holding it can call APIs with the token's permissions.

**Never** echo the token in `/api/me` responses or write it to logs, message queues, or analytics just to debug claims. When observability is needed, prefer correlation IDs and non-sensitive metadata.

### 15.4. Assuming OIDC ID Tokens and JWT Access Tokens Are the Same

An OIDC client holds `OidcUser` and ID Tokens, whereas a Resource Server requires an **access token targeted at the API**. Sharing an issuer and JWT format does not make an ID Token usable as an access token. Always validate audience and token type/profile.

### 15.5. Assuming `@AuthenticationPrincipal Jwt` Checks Permissions Automatically

The annotation only retrieves the principal from `SecurityContext`. It does not require `orders.read`, verify tenants, or guarantee the user is allowed to read a specific record.

### 15.6. Confusing `Authentication#getName()` with an Immutable Identity Key

The authentication name may be derived by a converter from an optional claim like `preferred_username`. For stable business keys, use `sub` within a trusted issuer context and per the token contract.

### 15.7. Assuming Every Claim Is Always Present

Not every JWT carries `client_id`, `tenant_id`, `email`, `roles`, or `locale`. Some claims belong to RFC 9068 profiles or specific issuers, so **never project one provider's claims onto every token**. Your API contract must specify required vs. optional claims, values, and types.

### 15.8. Granting Privileges Simply Because a Custom `roles` Claim Exists

A `roles` claim only drives authorization if the system defines explicit policies and a converter/validator for it. Never accept role strings unapproved by the issuer/application, and never map every role blindly to admin access.

### 15.9. Failing to Handle Nullable Principals on Public Endpoints

On a `permitAll` route without a Bearer token, the `Jwt` parameter may be null. Calling `jwt.getSubject()` directly causes a 500 error. If an endpoint is genuinely public, define explicit guest behavior.

### 15.10. Using `SecurityContextHolder` Arbitrarily in Background Tasks

`SecurityContext` is normally tied to the request/thread lifecycle. With asynchronous execution or event processing, never assume the request context automatically exists across threads. Pass an explicit identity context and only use actively configured context propagation.

## 16. Practical Example: “Who Am I?” Endpoint

### 16.1. Contract

Endpoint:

~~~http
GET /api/me
Authorization: Bearer <JWT_ACCESS_TOKEN>
~~~

Requirements:

- Token must be issued by `https://id.example.test/realms/shop`.
- `aud` must contain `orders-api`.
- `sub` is a non-blank String per contract.
- `tenant_id` is a non-blank String.
- `preferred_username` is an optional claim used only for display.
- Endpoint does not return the raw JWT or all claims.

Expected response:

~~~json
{
  "subject": "user-123",
  "tenantId": "tenant-42",
  "displayName": "phuong"
}
~~~

### 16.2. Controller

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public MeResponse me(@AuthenticationPrincipal Jwt jwt) {

        // Assumes JWT validators guarantee sub/tenant_id.
        String subject = jwt.getSubject();
        String tenantId = (String) jwt.getClaim("tenant_id");

        // Used for UI only; not as an identity key.
        String displayName =
            jwt.getClaimAsString("preferred_username");

        return new MeResponse(subject, tenantId, displayName);
    }

    public record MeResponse(
        String subject,
        String tenantId,
        String displayName
    ) {}
}
~~~

If `preferred_username` is absent, `displayName` may be null. JSON null/omission formatting depends on Jackson configuration; document the response contract clearly if clients rely on it.

### 16.3. Testing the Call

~~~bash
curl -i \
  -H "Authorization: Bearer <VALID_ORDERS_ACCESS_TOKEN>" \
  https://api.example.test/api/me
~~~

When the token is valid and contains the required claims, the controller receives `Jwt` and builds the response. The following requests are rejected before the controller by the appropriate security checks:

- Forged tokens or invalid signatures.
- Expired tokens.
- Tokens whose `iss` does not match a trusted issuer.
- Tokens whose `aud` does not include Orders API.
- Tokens missing `tenant_id` when the required-claim validator is enabled.

Never test by taking a production JWT and editing its payload directly: editing the payload invalidates the signature; to test claim logic accurately, use a controlled test issuer and test keys.

## 17. Summary of Options

| Need | Solution |
|---|---|
| Read `sub` of a verified JWT | `@AuthenticationPrincipal Jwt jwt` then `jwt.getSubject()` |
| Read issuer, audience, expiration | `getIssuer()`, `getAudience()`, `getExpiresAt()` |
| Read a custom claim | `getClaim("tenant_id")` or type-safe helper |
| Read a single value directly | `@AuthenticationPrincipal(expression = "subject")` |
| Read converted authorities/scopes | Inject `Authentication`, call `getAuthorities()` |
| Custom claim required for permissions/tenant | Validate via `OAuth2TokenValidator<Jwt>` before controller |
| Public endpoint where JWT may be absent | Handle `jwt == null` explicitly |
| OIDC login principal | `@AuthenticationPrincipal OidcUser` |
| Opaque token principal | `OAuth2AuthenticatedPrincipal` or `Authentication` |
| Rich business logic across services | Map `Jwt` to a typed `CallerIdentity`/context |
| Endpoint permissions | `authorizeHttpRequests` or method security |
| Per-record permissions | Service/repository checks owner/tenant/ACL |

**Key takeaway:** `@AuthenticationPrincipal Jwt` bridges a **JWT access token verified by Spring Security** into a **Spring MVC controller**. It simplifies reading claims, yet the annotation itself **does not replace JWT validation, does not grant permissions, and does not guarantee optional claims are present**.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Servlet MVC Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html)
- [Spring Security API — AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/annotation/AuthenticationPrincipal.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
- [Spring Security API — JwtAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

