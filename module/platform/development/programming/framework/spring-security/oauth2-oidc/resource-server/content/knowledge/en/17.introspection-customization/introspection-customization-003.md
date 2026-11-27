# Normalizing the Principal and Mapping Roles and Permissions After Introspection

In **Spring Security OAuth 2.0/OIDC Resource Server**, an opaque access token usually does not carry a JWT payload that the API can read and verify on its own. Instead, the Resource Server sends the token to the Authorization Server's (AS) **OAuth 2.0 Token Introspection Endpoint**. Once the AS confirms the token is valid, Spring Security constructs an `OAuth2AuthenticatedPrincipal` containing attributes and `GrantedAuthority` instances that the API can use for authorization.

A common practical need is **normalizing the principal** and **mapping roles and permissions** when the AS response does not completely match the application's data model. For instance, the AS returns `sub`, `username`, `scope`, `roles`, `permissions`, and `tenant_id`, while Spring Security endpoints need strings such as `SCOPE_orders.read`, `ROLE_ORDERS_MANAGER`, or `PERM_ORDERS_EXPORT`.

The easiest mistake to make is confusing:

- **Normalization:** changing how data *from a trusted source* is represented while preserving identity and permission semantics.
- **Granting permissions:** inserting a new authority into `Authentication` so the application permits an operation that was not previously proven valid.

> **Core principle:** the token must be introspected successfully first, and only then should you map roles/permissions granted by an authoritative source under an explicit contract. Never infer `ROLE_ADMIN` from a username, email, unfamiliar group name, or client-modifiable data.

This lesson focuses on **`OpaqueTokenIntrospector` and `OAuth2AuthenticatedPrincipal`**, avoiding mistakenly using `JwtAuthenticationConverter`, which belongs to the JWT processing path. Examples are based on Java 17+, Spring Boot, and Spring Security Servlet/Spring MVC. Package/API names may differ by Spring Boot/Spring Security version; refer to the documentation for your project's exact version.

## 1. Where Do Opaque Tokens and Introspection Sit in the Authentication Flow?

A request sends a bearer token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer 8fa7c...opaque-token...
~~~

Conceptually, the Resource Server processes it as follows:

~~~text
Client
  |
  | Authorization: Bearer <token>
  v
BearerTokenAuthenticationFilter
  |
  v
OpaqueTokenAuthenticationProvider
  |
  v
OpaqueTokenIntrospector
  |
  | Calls trusted endpoint using Resource Server credentials
  v
Authorization Server /introspect
  |
  +-- {"active": false} --> authentication failure
  |
  +-- {"active": true, "sub": ..., "scope": ..., ...}
  |
  v
OAuth2AuthenticatedPrincipal
  |
  +-- normalize display/identity attributes
  +-- preserve granted OAuth scopes
  +-- map approved roles/permissions
  v
BearerTokenAuthentication
  |
  v
SecurityContext -> HTTP / method / business authorization
~~~

Introspection is part of **authentication**, whereas role/permission conversion prepares data for **authorization**. It is meaningful only after the AS confirms the token is accepted.

**Do not** parse an opaque token as a JWT to trust `sub`, `roles`, or `permissions`. Even if a token has a three-segment shape like a JWT, the `opaqueToken()` configuration still uses the introspection result as the basis of authentication.

### 1.1. What Attributes Does RFC 7662 Return?

An illustrative response from the introspection endpoint:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-frontend",
  "scope": "orders.read orders.write",
  "token_type": "Bearer",
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "exp": 2000000300,
  "iat": 2000000000,
  "username": "alice",
  "roles": ["orders_reader"],
  "permissions": ["orders.export"],
  "tenant_id": "merchant-a"
}
~~~

This is an **example system contract**, not a mandatory response. RFC 7662 defines `active` and several optional attributes, while `roles`, `permissions`, and `tenant_id` are extensions defined by the AS/provider.

If the token is invalid, the AS usually returns:

~~~json
{
  "active": false
}
~~~

An `active=false` result **must not** produce an authenticated principal. The standard introspector must reject this token, and a custom decorator must never "recover" it by creating a `DefaultOAuth2AuthenticatedPrincipal`.

## 2. Spring Security Components to Distinguish

| Component | Responsibility | Notes When Customizing |
|---|---|---|
| `BearerTokenAuthenticationFilter` | Extracts the bearer token from the request | Do not use to guess roles |
| `BearerTokenAuthenticationToken` | Unauthenticated credential | Not a trusted principal |
| `OpaqueTokenAuthenticationProvider` | Invokes the introspector to authenticate | Succeeds only when the introspector returns a valid result |
| `OpaqueTokenIntrospector` | `introspect(String token)` | Preferred extension point in this lesson |
| `SpringOpaqueTokenIntrospector` | Calls standard introspection endpoint | Can be wrapped with a decorator |
| `OAuth2AuthenticatedPrincipal` | Principal name, attributes, authorities | Not a `Jwt` |
| `DefaultOAuth2AuthenticatedPrincipal` | Implementation constructible from name/attributes/authorities | Used for normalization |
| `BearerTokenAuthentication` | Authentication for an opaque bearer token | Placed into SecurityContext |
| `OpaqueTokenAuthenticationConverter` | Converts introspection result into Authentication | Use when changing the Authentication type is needed |

By default in Spring Security, `Authentication#getPrincipal()` for an opaque token is typically `OAuth2AuthenticatedPrincipal`, and `Authentication#getName()` usually comes from `sub` if introspection returns a subject. A JWT-handling API might use `@AuthenticationPrincipal Jwt`, whereas an opaque-token API should use `OAuth2AuthenticatedPrincipal` or an appropriate domain adapter.

### Two Processing Paths Not to Confuse

~~~text
JWT:
Bearer -> JwtDecoder -> Jwt -> JwtAuthenticationConverter
                         |
                         v
               JwtAuthenticationToken

Opaque token:
Bearer -> OpaqueTokenIntrospector -> OAuth2AuthenticatedPrincipal
                                     |
                                     v
                              BearerTokenAuthentication
~~~

A project can support both, provided each path is configured and tested properly. Creating a `JwtAuthenticationConverter` does not automatically change how `opaqueToken()` maps roles/permissions.

## 3. Configuring a Resource Server Using Introspection

Example Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

Introspection endpoint details and client credentials must be supplied through an appropriate configuration/secret management mechanism. Never hardcode secrets in source code or include them in logs. The endpoint URL depends on the actual AS; there is no default path for every IdP.

HTTP configuration:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

This filter chain only illustrates authentication and HTTP authorization. CORS/CSRF policies, cookies/sessions, and per-order permissions must be handled according to your specific architecture. Never disable CSRF unconditionally just because the application uses OAuth2.

### 3.1. How Does Spring Security Map Scopes by Default?

When the introspection response contains:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

Spring Security typically converts those scopes into:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

This is a representation conversion of **scopes already granted by the AS**. The `SCOPE_` prefix is a Spring Security convention; it does not mean the AS granted two new permissions.

To protect an endpoint by scope:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

There is no need to write a custom introspector merely to turn `orders.read` into `SCOPE_orders.read` if the default already handles it properly.

## 4. Principal Identity vs. Display Name and Entitlements

An introspection response may return:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-frontend",
  "username": "alice",
  "email": "alice@example.com"
}
~~~

These fields serve different purposes:

| Attribute | Proper Interpretation | Does Not Prove on Its Own |
|---|---|---|
| `sub` | Subject issued by the AS | User is an admin |
| `iss` | Issuer if returned by the AS | `sub` is unique across all issuers |
| `client_id` | OAuth client receiving the token | A specific human user |
| `username` | Account name, often mutable | Permissions on resources |
| `email` | Contact address, mutable | Enterprise role |
| `name` / `preferred_username` | Display name | API management permission |
| `tenant_id` | Tenant context | Tenant admin |
| `roles` / `permissions` | Custom entitlements per contract | Permissions in any other application |

### 4.1. Using a Stable Identifier

For user tokens, `sub` is a common choice for subject ID, but when accepting multiple issuers you must consider the **`(issuer, subject)` pair**. For example:

~~~text
(https://idp-a.example.com, user-42) -> Person A
(https://idp-b.example.com, user-42) -> Person B
~~~

Two identical `sub` values are not enough to merge accounts. Never merge identities merely because email or username matches.

If the introspection endpoint does not return `iss`, the application can determine the issuer namespace from the **trusted configured introspection endpoint**, provided each endpoint serves only a single issuer under contract. Never take the issuer from a client-sent header/query or guess it from the hostname of an untrusted URL.

### 4.2. Distinguishing User Tokens from Machine Tokens

In `client_credentials`, a token may represent an application/process rather than a human user. A response may contain `client_id=nightly-importer` with or without `sub` depending on the AS.

Do not apply logic like:

~~~text
Has sub -> definitely a human user -> automatically add ROLE_USER
~~~

You must distinguish principal models per the AS contract: user subject, machine client, tenant/application, and granted permissions. For machines, `client_id` can be the primary workload identifier, but must not be turned into a human user identity.

### 4.3. Display Name Should Be Separated from the Name Used for Ownership

For example:

~~~text
Canonical name = user-42
Display name   = Alice Smith
Authorities    = [SCOPE_orders.read]
~~~

Changing `display_name` for the UI should not change `Authentication#getName()` if the service layer uses `getName()` to look up ownership in the database. If you need to map to an internal user ID, use a controlled mapping from `(issuer, sub)` and never assign high default permissions when the mapping does not exist.

## 5. Scopes, Roles, and Permissions Are Not the Same Kind of Information

| Authority | Expected Source | Used to Check |
|---|---|---|
| `SCOPE_orders.read` | OAuth scope granted by the AS | `hasAuthority("SCOPE_orders.read")` |
| `SCOPE_orders.write` | OAuth write scope granted by the AS | `hasAuthority("SCOPE_orders.write")` |
| `ROLE_ORDERS_READER` | Application role granted authoritatively | `hasRole("ORDERS_READER")` |
| `ROLE_ORDERS_MANAGER` | Application role granted authoritatively | `hasRole("ORDERS_MANAGER")` |
| `PERM_ORDERS_EXPORT` | Granular permission per application policy | `hasAuthority("PERM_ORDERS_EXPORT")` |
| `PERM_REFUND_APPROVE` | Refund approval permission | `hasAuthority("PERM_REFUND_APPROVE")` |

`PERM_` is an **illustrative application convention**, not a Spring Security default prefix. `hasRole("ORDERS_MANAGER")` normally checks for the `ROLE_ORDERS_MANAGER` authority, not `SCOPE_orders.manager`.

### 5.1. Entitlement Claims Must Be Authoritative

Suppose the response has:

~~~json
{
  "active": true,
  "roles": ["orders_reader"],
  "permissions": ["orders.export"]
}
~~~

Conditions for mapping them into API roles/permissions:

1. The AS issues these claims from an **organization-trusted authorization source**, not a user-editable profile field.
2. Permissions belong to the **`orders-api` application**, not roles from another console or client.
3. Permissions have well-defined semantics, tenant scope, and actions.
4. Mapping from source names to target authorities uses an **approved allowlist**.
5. Roles/permissions do not automatically bypass ownership/tenant checks in the service.
6. Grant and revocation lifecycles are designed in line with token TTL / introspection caching.

Even if the AS returns `active=true`, a claim `username="admin-support"` does not mean the user was granted `ROLE_ADMIN`. An AS may sign or return self-declared profile attributes without giving them authorization authority.

## 6. Intentional Role and Permission Mapping Table

Example `orders-api` contract:

| Introspection Value | Authority After Mapping | Rule |
|---|---|---|
| `scope` contains `orders.read` | `SCOPE_orders.read` | Preserve from delegate |
| `scope` contains `orders.write` | `SCOPE_orders.write` | Preserve from delegate |
| `roles=["orders_reader"]` | `ROLE_ORDERS_READER` | Approved roles only |
| `roles=["orders_manager"]` | `ROLE_ORDERS_MANAGER` | Do not infer system-wide admin |
| `permissions=["orders.export"]` | `PERM_ORDERS_EXPORT` | Valid API permission |
| `permissions=["refund.approve"]` | `PERM_REFUND_APPROVE` | Still verify merchant/limits |
| `roles=["unknown_admin"]` | No authority added | Never auto-map unknown values |
| No `roles` | No role added | Never create a default admin |
| No `permissions` | No permission added | Never invent permissions to avoid 403 |
| Wrong-typed claim | Reject or fail closed per contract | Never guess arbitrary formats |

**String normalization must not alter permission semantics.** If two ASes both have a role called `operator`, yet in AS A it means customer support while in AS B it means order manager, you cannot map both to the same `ROLE_ORDERS_MANAGER`.

Scope mappings by **issuer, client/audience, application, and namespace**, rather than mapping any similar-looking role string globally.

## 7. Why Use a Decorator for `OpaqueTokenIntrospector`?

A safe extension pattern is wrapping an existing implementation:

~~~text
MappingOpaqueTokenIntrospector
        |
        | delegate.introspect(token)
        v
SpringOpaqueTokenIntrospector
        |
        +-- active=false / invalid -> exception
        |
        +-- active=true -> verified OAuth2AuthenticatedPrincipal
                               |
                               +-- keep principal name
                               +-- normalize display attributes
                               +-- keep original SCOPE_ authorities
                               +-- map allowlisted roles/permissions
                               |
                               v
                   DefaultOAuth2AuthenticatedPrincipal
~~~

This way, the custom class does not have to reimplement HTTP introspection requests, client authentication, RFC 7662 parsing, or inactive token handling. It only adds **post-authentication normalization/mapping** logic.

Never implement something like this:

~~~java
// WRONG: token not verified yet, already returning an admin principal.
return new DefaultOAuth2AuthenticatedPrincipal(
    "user",
    Map.of("active", true),
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
~~~

That bypasses the authentication boundary.

## 8. Java: Custom Introspector Normalizing Principal and Mapping Permissions

Suppose the AS guarantees:

- `scope`: standard OAuth scope, already converted by the delegate into `SCOPE_*`.
- `roles`: an **array of strings** issued by the AS from the application-role database.
- `permissions`: an **array of strings** issued by the AS from the permission catalog.
- `username`: display field, never used to grant permissions.
- Unknown role/permission values: do not map.
- Wrong-typed role/permission claims: reject as contract violation.

### 8.1. Complete Implementation

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class MappingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    // These mappings are POLICY and must be approved.
    private static final Map<String, String> ROLE_MAP = Map.of(
        "orders_reader", "ROLE_ORDERS_READER",
        "orders_manager", "ROLE_ORDERS_MANAGER"
    );

    private static final Map<String, String> PERMISSION_MAP = Map.of(
        "orders.export", "PERM_ORDERS_EXPORT",
        "refund.approve", "PERM_REFUND_APPROVE"
    );

    private final OpaqueTokenIntrospector delegate;

    public MappingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // The delegate verifies the token via introspection.
        // If the token is inactive, the delegate must throw an exception.
        OAuth2AuthenticatedPrincipal verified =
            delegate.introspect(token);

        // Preserve SCOPE_* authorities already granted by the delegate.
        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(verified.getAuthorities());

        addMappedAuthorities(
            verified.getAttribute("roles"),
            ROLE_MAP,
            authorities,
            "roles"
        );

        addMappedAuthorities(
            verified.getAttribute("permissions"),
            PERMISSION_MAP,
            authorities,
            "permissions"
        );

        Map<String, Object> attributes =
            new LinkedHashMap<>(verified.getAttributes());

        // Normalize DISPLAY field only.
        Object rawUsername = attributes.get("username");
        String displayName =
            rawUsername instanceof String username
                && !username.isBlank()
                ? username
                : verified.getName();

        attributes.put("display_name", displayName);

        // Do not change canonical principal name or fabricate scopes.
        return new DefaultOAuth2AuthenticatedPrincipal(
            verified.getName(),
            attributes,
            authorities
        );
    }

    private static void addMappedAuthorities(
            Object raw,
            Map<String, String> mapping,
            Set<GrantedAuthority> target,
            String claimName) {

        // Optional claim absent -> grant no permission.
        if (raw == null) {
            return;
        }

        // Per contract, roles/permissions is an array of strings.
        if (!(raw instanceof Collection<?> values)) {
            throw new BadOpaqueTokenException(
                "Unexpected " + claimName + " claim type"
            );
        }

        for (Object item : values) {
            if (!(item instanceof String value)) {
                throw new BadOpaqueTokenException(
                    "Invalid item in " + claimName
                );
            }

            String mapped = mapping.get(value);
            if (mapped != null) {
                target.add(new SimpleGrantedAuthority(mapped));
            }
        }
    }
}
~~~

**Security properties of this example:**

- `delegate.introspect(token)` runs **before** any mapping. Inactive tokens are never mapped.
- Original scope permissions from the delegate are preserved, not replaced by custom roles.
- Only roles/permissions present in the allowlist get an authority added.
- No `ROLE_ADMIN`/`SCOPE_orders.write` appears spontaneously when not granted by the source.
- Unknown role/permission values are not mapped automatically.
- Wrong-typed claims are rejected per contract rather than parsed "until readable."
- `display_name` is for display only; `getName()` is not replaced with email or username.
- `LinkedHashSet` deduplicates authorities without inventing permissions.

**Limitation:** `roles` and `permissions` are hypothetical AS claims. If a provider returns nested objects or delimited strings, design an appropriate parser **according to the AS's official documentation** rather than modifying the example by guesswork.

### 8.2. Why Not Replace All Authorities?

A wrong implementation:

~~~java
return new DefaultOAuth2AuthenticatedPrincipal(
    verified.getName(),
    verified.getAttributes(),
    customRoleAuthoritiesOnly
);
~~~

can **drop** the `SCOPE_*` authorities extracted by Spring. Then an API requiring `SCOPE_orders.read` will fail with 403 even though introspection indicated the token had that scope.

On the other hand, adding `SCOPE_orders.write` when the token only has `orders.read` is **unfounded privilege granting**. `verified.getAuthorities()` must be kept, adding only permissions backed by recognized entitlements.

### 8.3. Should Other Authorities Be Removed?

A system might intentionally retain only the subset of authorities relevant to `orders-api`. **Filtering out** unused permissions can align with least privilege, provided you check which authorities other parts of the system rely on. Never automatically convert arbitrary unknown authorities into similarly named application permissions.

In newer Spring Security versions, authentication may also include factor authorities such as `FACTOR_BEARER`. Never treat such technical authorities as business permissions or attempt to convert them into scopes.

## 9. Registering the Wrapper Introspector in Spring Boot

When you provide an `OpaqueTokenIntrospector` bean, Spring Boot normally **stops creating the default introspector**. Therefore, you must explicitly create a real delegate and wrap it.

### 9.1. Spring Boot 3.x Using `OAuth2ResourceServerProperties`

~~~java
package com.example.orders.security;

import org.springframework.boot.autoconfigure.security.oauth2.resource.OAuth2ResourceServerProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            OAuth2ResourceServerProperties properties) {

        var opaque = properties.getOpaquetoken();

        String uri = opaque.getIntrospectionUri();
        String id = opaque.getClientId();
        String secret = opaque.getClientSecret();

        if (uri == null || uri.isBlank()
                || id == null || id.isBlank()
                || secret == null || secret.isBlank()) {
            throw new IllegalStateException(
                "Missing opaque token introspection configuration"
            );
        }

        OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(id)
                .clientSecret(secret)
                .build();

        return new MappingOpaqueTokenIntrospector(delegate);
    }
}
~~~

This snippet reuses the URI/client ID/client secret from `application.yml`. In Spring Boot 4.x, the package of `OAuth2ResourceServerProperties` changes; check imports for your version (for example, the `org.springframework.boot.security.oauth2.server.resource.autoconfigure` package group). Spring Security APIs like `OpaqueTokenIntrospector` and `SpringOpaqueTokenIntrospector` have their own packages.

Never log `secret` or endpoint responses in startup errors. Example strings use placeholder domains; real environments must read from access-controlled configuration.

### 9.2. Alternative Using `@Value`

If you do not want to depend on Boot's properties class, you can inject properties directly:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

    OpaqueTokenIntrospector delegate =
        SpringOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return new MappingOpaqueTokenIntrospector(delegate);
}
~~~

Import `org.springframework.beans.factory.annotation.Value`, `org.springframework.context.annotation.Bean`, and related imports. **Choose one** bean registration approach—do not accidentally declare two introspector beans at the same time.

### 9.3. Do Not Write a Stub Introspection for Production

Wrong:

~~~java
@Bean
OpaqueTokenIntrospector introspector() {
    return token -> new DefaultOAuth2AuthenticatedPrincipal(
        "demo-user", Map.of("sub", "demo-user"), List.of()
    );
}
~~~

The stub bypasses checking whether the AS confirmed the token is active. It may suit demos/mocks in unit tests, but deploying it to production creates a critical authentication vulnerability.

## 10. When to Use a Custom `OpaqueTokenAuthenticationConverter`?

There are two distinct needs:

1. **Changing principal attributes and authorities:** use an `OpaqueTokenIntrospector` decorator as shown above.
2. **Changing the final `Authentication` type:** use `OpaqueTokenAuthenticationConverter` when the application needs a specialized `Authentication` or needs to integrate the security context with another system.

The `OpaqueTokenAuthenticationConverter` API receives the token after successful introspection and the `OAuth2AuthenticatedPrincipal`, and returns an `Authentication`:

~~~java
Authentication convert(
    String introspectedToken,
    OAuth2AuthenticatedPrincipal authenticatedPrincipal
);
~~~

This is a **post-introspection** extension point, not a place to bypass AS validation. For typical role/permission mapping needs, an introspector decorator is cleaner and changes less framework structure.

If using a custom authentication converter, preserve all properties and contracts required by Spring Security: principal, credentials, authorities, authenticated state, no token leakage via logs/`toString()`, and compatibility with `AuthorizationManager`s. Registration steps may vary by Spring Security version.

## 11. Controller Accessing the Normalized Principal

In an opaque-token Resource Server, you can inject:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String name = principal.getName();
        String display = principal.getAttribute("display_name");

        if (display == null || display.isBlank()) {
            display = name;
        }

        return Map.of("id", name, "displayName", display);
    }
}
~~~

The example assumes `GET /api/me` is protected with `authenticated()` and the principal has a valid name. `display_name` may be added by the decorator; otherwise, the controller falls back to `name`.

**Never return raw attributes directly in a response** just for debugging. An introspection response may contain PII, client metadata, or entitlement data that should not be exposed. Return only the fields the product requires.

### Reading Authorities

When checking permissions:

~~~java
boolean canExport = principal.getAuthorities().stream()
    .anyMatch(a ->
        "PERM_ORDERS_EXPORT".equals(a.getAuthority()));
~~~

In business code, prefer Spring Security `@PreAuthorize`, `AuthorizationManager`, or service policy instead of scattering string checks across controllers. That keeps testing and permission management consistent.

## 12. Protecting Endpoints Based on Mapped Authorities

Suppose the policy for `orders-api` is:

| Endpoint | Condition |
|---|---|
| `GET /api/me` | `authenticated()` |
| `GET /api/orders/**` | `SCOPE_orders.read` |
| `POST /api/orders/**` | `SCOPE_orders.write` |
| `GET /api/exports/**` | `PERM_ORDERS_EXPORT` |
| `POST /api/refunds/**` | `PERM_REFUND_APPROVE` and business policy |
| `/api/management/**` | `ROLE_ORDERS_MANAGER` |
| Other endpoints | `denyAll()` |

Illustrative configuration:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/me")
        .authenticated()
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.GET, "/api/exports/**")
        .hasAuthority("PERM_ORDERS_EXPORT")
    .requestMatchers(HttpMethod.POST, "/api/refunds/**")
        .hasAuthority("PERM_REFUND_APPROVE")
    .requestMatchers("/api/management/**")
        .hasRole("ORDERS_MANAGER")
    .anyRequest().denyAll()
)
~~~

### The `ROLE_` Prefix Is Not Added Automatically from `roles`

`hasRole("ORDERS_MANAGER")` normally requires the `ROLE_ORDERS_MANAGER` authority. Spring Security does not automatically read arbitrary `roles`/`permissions` claims from every IdP and turn them into matching authorities. It is the **mapping wrapper** defined in this lesson that does that according to the contract.

### Broad Permissions Are Not Enough for a Specific Object

`PERM_REFUND_APPROVE` does not prove the caller can approve every refund. The service must also verify merchant, limits, payment status, separation of creator and approver, and transaction atomicity.

A `tenant_id` from a token or URL does not by itself prove permission to manage that tenant either. You need membership/ownership from an authoritative source and tenant-scoped data queries to prevent BOLA/IDOR vulnerabilities.

## 13. Can Permissions from Introspection Become Stale?

An advantage of introspection is that the AS can tell whether a token has been revoked at call time. However, role/permission freshness still depends on:

- Whether the AS updates entitlements immediately upon change.
- Whether the AS caches roles or directory sources.
- Whether the Resource Server caches introspection results.
- Whether a gateway caches authorization decisions.
- Whether the business authorization system requires querying current state.

For example:

~~~text
10:00  Token is issued with role orders_manager
10:02  Admin revokes orders_manager
10:03  Resource Server checks token
~~~

If introspection returns the updated roles, the mapping will not add `ROLE_ORDERS_MANAGER`. But if a response/cache still contains the old role, the API may continue accepting it within the designed stale window.

Do not claim that introspection **automatically** solves all revocation/permission freshness problems. For sensitive actions, consider checking current entitlements in the service or a dedicated policy engine.

## 14. Multi-Issuer and Tenant Isolation

If the API supports multiple ASes:

~~~text
IdP A -> roles=["operator"]
IdP B -> roles=["operator"]
~~~

the two `operator` values can have different meanings. A shared mapping:

~~~text
operator -> ROLE_ORDERS_MANAGER
~~~

is valid only if both ASes are approved and share an equivalent contract for `orders-api`.

The design must determine:

1. Which issuer/AS the token belongs to, via a trusted introspection endpoint.
2. Which namespace the subject belongs to.
3. Which application the role/permission claims apply to.
4. Which source validates tenant binding.
5. Whether the principal has permission on the specific resource.

**Never** choose the introspection URL directly from an unverified claim/token or a client-sent header. That can cause SSRF or make the Resource Server trust an attacker-controlled endpoint.

### Avoid Merging Identities by Username

Two people in two IdPs can share `username=alice`; they remain two independent principals. If internal user mapping is needed, use `(issuer, sub)` or an AS-contracted identifier, never just `username` or email.

## 15. Role Mapping Must Not Become Privilege Escalation

Typical anti-patterns:

### 15.1. Relying on Email

~~~java
// WRONG: profile attributes do not prove administrative rights.
if (email.endsWith("@company.example")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

### 15.2. Relying on a Name Containing "admin"

~~~java
// WRONG: could derive roles from display data.
if (username.startsWith("admin")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

### 15.3. Defaulting All Permissions When Claims Are Missing

~~~java
// WRONG: missing claim must never mean full access.
if (roles == null) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ORDERS_MANAGER"));
}
~~~

### 15.4. Turning Any Role String into an Internal Permission

~~~java
// WRONG unless roles are namespaced and mapped under contract.
for (String role : roles) {
    authorities.add(new SimpleGrantedAuthority(
        "ROLE_" + role.toUpperCase()
    ));
}
~~~

### 15.5. Automatically Upgrading a Read Scope to a Write Scope

~~~java
// WRONG: the application must not fill in missing scopes.
if (authorities.contains(
        new SimpleGrantedAuthority("SCOPE_orders.read"))) {
    authorities.add(
        new SimpleGrantedAuthority("SCOPE_orders.write"));
}
~~~

**How to prevent this:** use allowlists with clear semantics, verify the entitlement source, handle unknown values by granting no permission, and write negative tests proving admin/write authorities never appear from identity attributes.

## 16. When Introspection Does Not Provide Issuer/Audience

RFC 7662 allows certain attributes to be absent from the response. Do not assume `iss` and `aud` are always present as in JWTs.

Valid architectural patterns include:

- An introspection endpoint **dedicated to a single audience/resource** where the AS already enforces access boundaries.
- An introspection response returning `aud` so the Resource Server can verify the token is intended for `orders-api`.
- An intermediary API gateway or authorization service with a contract asserting resource binding.
- The Resource Server calling a dedicated introspection endpoint per approved issuer/tenant.

If the contract requires `aud` yet the response lacks it, never patch the response to `"aud":["orders-api"]` just to pass validation. Fix the contract with the AS or choose another verification mechanism.

Conceptual validator example:

~~~java
Object rawAudience = verified.getAttribute("aud");

if (!audienceMatchesOrdersApi(rawAudience)) {
    throw new BadOpaqueTokenException(
        "Token is not intended for orders-api"
    );
}
~~~

`audienceMatchesOrdersApi` is an application-defined helper; it must handle the string/list schema per the AS contract and is not a built-in Spring Security API. Some systems do not need this additional validator if the introspection endpoint already enforces resource binding authoritatively; clarify this before choosing.

## 17. Wrong-Typed Claims, Missing Claims, and Fallbacks

A contract must specify behavior for unexpected responses:

| Case | Safe Behavior |
|---|---|
| `active=false` | Authentication failure |
| `roles` absent | No new role |
| `permissions` absent | No new permission |
| `roles=[]` | No new role |
| `roles=["orders_reader"]` | Map approved role |
| `roles=["unknown_admin"]` | Do not map elevated privilege |
| `roles="orders_reader"` when contract requires an array | Reject malformed schema |
| `permissions=[1, "orders.export"]` | Reject wrong-typed item |
| `scope` absent | Do not invent scopes |
| `sub` absent in a user-token contract requiring subject | Reject or handle separately by token kind |
| `client_id` present on a machine token | Apply the machine identity contract |
| Introspection endpoint timeout | Never allow by default |
| Role from another client/issuer | Do not reuse out-of-scope mapping |

Do not write a parser saying "if it's a string, split on commas; if it's an object, take all keys; if it's a list, flatten all values" unless the AS specifies that. Uncontrolled schema relaxation easily turns a claim with a different meaning into an entitlement.

## 18. Testing the Converter with a Mock Delegate

Unit testing mapping does not require calling a real AS. Create a delegate returning a mock principal to isolate mapping logic.

~~~java
package com.example.orders.security;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MappingOpaqueTokenIntrospectorTest {

    @Test
    void preservesScopesAndMapsOnlyApprovedRights() {
        OpaqueTokenIntrospector delegate = token ->
            new DefaultOAuth2AuthenticatedPrincipal(
                "user-42",
                Map.of(
                    "sub", "user-42",
                    "username", "admin-support",
                    "roles", List.of(
                        "orders_reader", "unknown_admin"),
                    "permissions", List.of("orders.export")
                ),
                List.of(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        OpaqueTokenIntrospector mapped =
            new MappingOpaqueTokenIntrospector(delegate);

        OAuth2AuthenticatedPrincipal principal =
            mapped.introspect("unit-test-token");

        Set<String> authorities = principal.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(
            Set.of(
                "SCOPE_orders.read",
                "ROLE_ORDERS_READER",
                "PERM_ORDERS_EXPORT"
            ),
            authorities
        );

        assertEquals("user-42", principal.getName());
        assertEquals(
            "admin-support",
            principal.getAttribute("display_name")
        );
    }
}
~~~

Even though `username` contains `admin`, the result **does not** contain `ROLE_ADMIN`. Even though `roles` contains `unknown_admin`, the mapping does not accept it.

### 18.1. Inactive Tokens Must Always Be Rejected

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.junit.jupiter.api.Assertions.assertThrows;

class InactiveTokenTest {

    @Test
    void doesNotCreatePrincipalWhenDelegateRejectsToken() {
        OpaqueTokenIntrospector delegate = token -> {
            throw new BadOpaqueTokenException("inactive");
        };

        var mapping = new MappingOpaqueTokenIntrospector(delegate);

        assertThrows(
            BadOpaqueTokenException.class,
            () -> mapping.introspect("inactive-token")
        );
    }
}
~~~

The decorator does not swallow the exception and grant roles. In production, the real delegate calls the introspection endpoint and handles `active=false`.

### 18.2. Wrong Types Must Fail Closed

~~~java
@Test
void rejectsWrongRoleClaimType() {
    OpaqueTokenIntrospector delegate = token ->
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-42",
            Map.of("roles", "orders_reader"),
            List.of()
        );

    var wrapper = new MappingOpaqueTokenIntrospector(delegate);

    assertThrows(
        BadOpaqueTokenException.class,
        () -> wrapper.introspect("test-token")
    );
}
~~~

Here `roles` is a string while the contract requires an array, so mapping rejects it. If your project's AS actually defines `roles` as a string, write a contracted parser and dedicated tests rather than treating an example format as universal.

## 19. HTTP and Introspection Integration Testing

Decorator unit tests only prove **Java mapping**, not that:

- The token was confirmed `active=true` by the AS.
- Introspection URI/client credentials are correct.
- HTTPS/truststore works properly.
- The AS response is parsed properly.
- `BearerTokenAuthentication` is built with production authorities.
- HTTP/method security is correct.
- Tenant/ownership policy is enforced.

Spring Security Test supports `opaqueToken()` for MockMvc:

~~~java
mvc.perform(get("/api/orders")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

The example assumes the endpoint exists and business code does not throw an error. **MockMvc `opaqueToken()` can bypass real introspection and mappers**, because the test supplies authorities directly. It is useful for testing HTTP authorization, not a replacement for integration tests.

A complete test suite should cover:

1. Unit tests mapping allowed roles/permissions.
2. Tests verifying unknown/malformed claims do not add permissions.
3. Stub introspection endpoint returning `active=true` with a valid payload.
4. Stub introspection endpoint returning `active=false` and verifying rejection.
5. Client credentials/TLS/error-handling tests per environment.
6. Tests verifying JWT-like input is still processed via introspection when opaque flow is chosen.
7. Tests for `401` on missing/invalid tokens and `403` when valid tokens lack authority.
8. Service tests for another tenant, another owner's order, and recently revoked permissions.
9. Tests verifying role mappings by issuer/client are not mixed.
10. Tests ensuring the production path does not accidentally use a mock introspector.

### 19.1. Expected Permission Matrix

| Introspection Result | Expected Additional Authorities | Example Decision |
|---|---|---|
| `active=false` | No authentication | 401 |
| `active=true`, `scope=orders.read` | `SCOPE_orders.read` | GET orders may be allowed |
| Only `orders.read`, calling POST | No `SCOPE_orders.write` | 403 |
| `roles=["orders_reader"]` | `ROLE_ORDERS_READER` | Only corresponding role rules |
| `roles=["unknown_admin"]` | No admin role | Admin endpoint rejected |
| `permissions=["orders.export"]` | `PERM_ORDERS_EXPORT` | Export endpoint passes authority layer |
| Missing `permissions` | No `PERM_*` | Permission-specific endpoint rejected |
| Has `PERM_REFUND_APPROVE`, refund in another tenant | Has general authority, rejected by object policy | 403/404 per design |
| Introspection service timeout | Do not grant | Infrastructure error or rejection per policy |

Exact `200`, `401`, and `403` statuses also depend on controllers, business services, handlers, and Spring Security configuration.

## 20. When to Use `RestClientOpaqueTokenIntrospector`?

Newer Spring Security versions add `RestClientOpaqueTokenIntrospector`, built on Spring's `RestClient`, allowing HTTP client and timeout customization.

What matters is **API version**: the `RestClientOpaqueTokenIntrospector` class appears in newer Spring Security lines (per Javadoc from 7.1). Do not copy a 7.1 example directly into a 6.x project and expect the class to exist.

In versions using `SpringOpaqueTokenIntrospector`, you can configure the HTTP client/timeouts through the API provided by that version. If you need custom features such as retries, circuit breakers, or metrics, prefer wrapping the standard client/delegate without losing token validation.

Never set infinite timeouts or auto-allow tokens when the endpoint does not respond. **Introspection unavailable does not mean the token is active.**

## 21. Caching Introspection Results and Permission Freshness

Every introspection call incurs network latency. Caching results can reduce load but introduces stale authorization:

~~~text
T0: AS returns active=true, role=orders_manager
T1: Admin revokes role
T2: Resource Server uses cached T0 response -> still sees old role
~~~

When designing a cache:

- Never cache past the token's expiration time if `exp` is present.
- Choose TTLs based on revocation and permission-update requirements.
- Never reuse results across different tokens or issuers.
- If the cache key uses the token, protect the token and avoid exposing raw tokens in logs/metrics.
- Consider invalidation when roles/membership change.
- Never fail open during temporary AS errors by using an expired allow-cache outside policy.
- If the API requires immediate revocation, consider checking entitlements in the service for sensitive actions.

**Opaque introspection does not automatically guarantee always-fresh permissions** if any layer caches or if the AS does not update permissions immediately.

## 22. Observability, Logging, and Error Handling

For diagnostics, log event categories instead of full tokens:

~~~text
event=opaque_principal_mapping
result=SUCCESS
principalRef=<stable-internal-id>
mappedRoleCount=1
mappedPermissionCount=1
source=trusted-introspection-endpoint
mappingPolicyVersion=v3
traceId=5e8c...
bearerToken=[REDACTED]
~~~

Do not log:

- Access tokens in the `Authorization` header.
- The introspection endpoint's client secret.
- Full responses containing PII or sensitive permissions.
- Usernames/emails unless needed for debugging and covered by protection policies.

Distinguish error groups:

| Error | Meaning | Handling Direction |
|---|---|---|
| `active=false` | Token is no longer accepted | Do not create principal |
| Wrong introspection URI | Cannot connect to right endpoint | Fix configuration |
| Wrong client credentials | Resource Server cannot authenticate to AS | Fix secret management and client auth |
| Wrong-typed roles/permissions | AS contract mismatch | Fix schema or parser |
| Unknown role | No approved mapping | Do not create authority |
| Mapper drops scopes | Delegate authorities not preserved | Fix mapping |
| HTTP 403 with active token | Missing authority or resource policy denied | Do not add permissions to mask the error |
| PDP/membership DB timeout | Authorization infrastructure unavailable | Fail closed, do not grant |
| Stale role after revocation | Cache/token lifetime/AS freshness | Review permission-update policy |

Infrastructure errors may return 5xx or other statuses depending on exception handlers; never turn every timeout into a fake `403` without distinguishing telemetry.

## 23. Common Misconceptions

**"Opaque tokens have no JWT payload, so they have no principal."** False. The principal is constructed from the **introspection attributes** of a verified valid token.

**"`Authentication#getPrincipal()` is always a `Jwt`."** False for the opaque flow. It is typically `OAuth2AuthenticatedPrincipal`.

**"`active=true` means every claim can be used to grant roles."** No. Claims must carry authorization semantics, come from an authoritative source, and target the right application.

**"Spring Security automatically maps `roles` and `permissions` fields from every IdP."** No. Defaults focus on OAuth scopes; custom claims require contracted mapping.

**"Just uppercase the group name and prepend `ROLE_`."** Dangerous. Another application's group could collide with an administrative role name.

**"Username containing admin means `ROLE_ADMIN`."** False. Usernames/display names do not prove entitlements.

**"If a permission is missing, assign a default permission to avoid 403."** Wrong unless an approved authorization policy explicitly grants it.

**"A custom introspector does not need to call the AS if we already know the role."** False. The token must be validly introspected first.

**"Roles in introspection are always fresh."** Not guaranteed; it depends on the entitlement source and caching.

**"An active token with an export permission can export any tenant."** False. Membership, ownership, and object-level policy must still be checked.

**"`opaqueToken()` can be customized with `JwtAuthenticationConverter`."** Wrong API path. Use `OpaqueTokenIntrospector`/`OpaqueTokenAuthenticationConverter`.

**"MockMvc `opaqueToken()` proves the production introspector is calling the AS."** No; mock authentication can bypass introspection.

## 24. Self-Check Questions

**1.** A response has `active=true, scope="orders.read orders.write"`. Which authorities does Spring Security typically create?

> `SCOPE_orders.read` and `SCOPE_orders.write`, after successful introspection.

**2.** In an opaque Resource Server, what type does the principal usually have?

> `OAuth2AuthenticatedPrincipal` inside `BearerTokenAuthentication`, not `Jwt`.

**3.** Why must the wrapper call `delegate.introspect(token)` first?

> To ensure the AS confirmed the token is valid; roles must never be mapped for an inactive token.

**4.** Is `username=admin-support` grounds for granting `ROLE_ADMIN`?

> No. Username is an identity/display attribute, not an entitlement.

**5.** When is it acceptable to map `roles=["orders_manager"]` to `ROLE_ORDERS_MANAGER`?

> When the AS issues the role from an authoritative source, intended for the right Resource Server, and the mapping is approved.

**6.** Why must `verified.getAuthorities()` be preserved?

> To avoid losing OAuth scopes already mapped by Spring from the valid response.

**7.** If `roles` has type string while the contract requires an array, what should be done?

> Treat it as a malformed response without guessing; reject the token per policy.

**8.** If a token only has `orders.read`, may the converter add `SCOPE_orders.write`?

> No. That is unfounded privilege escalation.

**9.** Is an opaque token with `PERM_REFUND_APPROVE` enough to refund any transaction?

> Not yet. Merchant, limits, payment status, and business policy must be checked inside the transaction.

**10.** Why must introspection caches be time-bounded?

> Because tokens/roles may be revoked or permissions changed; stale caches could continue allowing unintended requests.

## 25. References

- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, default principal, scope mapping, custom introspector, HTTP client.
- [Spring Security — OpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): `introspect(String)`.
- [Spring Security — SpringOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html): standard introspection client.
- [Spring Security — OAuth2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html): attributes, authorities, and principal name.
- [Spring Security — DefaultOAuth2AuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html): normalizing the principal.
- [Spring Security — OAuth2IntrospectionAuthenticatedPrincipal API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OAuth2IntrospectionAuthenticatedPrincipal.html): principal for introspection responses.
- [Spring Security — OpaqueTokenAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenAuthenticationConverter.html): customizing Authentication after introspection.
- [Spring Security — BearerTokenAuthentication API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html): opaque bearer authentication.
- [Spring Security — BadOpaqueTokenException API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/BadOpaqueTokenException.html): invalid token/response handling.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): opaque token properties and auto-configuration.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope`, `client_id`, `sub`, and introspection contract.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer credentials and authentication errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): scopes and access tokens.

**Summary:** keep the boundary clear—**introspect the token validly first**, and only then **normalize identity and map granted entitlements**. Principal names must be stable; display names must never be turned into roles. Default scopes must be preserved, custom roles/permissions require an authoritative allowlist, and permissions on specific tenants/resources must still be enforced at the business layer.
