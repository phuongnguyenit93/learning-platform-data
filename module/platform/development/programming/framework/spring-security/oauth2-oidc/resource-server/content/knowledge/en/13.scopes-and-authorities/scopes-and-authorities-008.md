# Combining Multiple Authority Sources Without Duplication or Unintended Privilege Escalation

## 1. Problem in OAuth 2.0 Resource Server

A Spring Security Resource Server can receive a JWT access token containing multiple permission-related pieces of information:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.export orders.read",
  "app_roles": ["ORDER_VIEWER", "ORDER_VIEWER", "ORDER_EDITOR"],
  "groups": ["customer-support"],
  "tenant_id": "tenant-42",
  "exp": 2000000000
}
~~~

This is an illustrative payload, not a real signed JWT. These fields have different meanings:

- `scope`: range delegated to the **specific access token**.
- `app_roles`: application roles, trustworthy only if the issuer is authorized to issue roles for that API.
- `groups`: organizational groups, not automatically equivalent to API roles.
- `tenant_id`: data boundary, not a global role.
- Local entitlements in the database: permissions owned by the application, which can change independently of the JWT.
- ACL/ownership: permissions for a specific record.

After verifying the JWT, Spring Security builds an `Authentication` containing `GrantedAuthority` instances. Merging sources carelessly can introduce two bugs:

1. **Duplicate authorities:** `SCOPE_orders.read` or `ROLE_ORDER_VIEWER` appears multiple times due to multiple converters or repeated claims.
2. **Unintended privilege escalation:** a source intended only to *constrain* permissions is accidentally used to *grant additional* permissions—for example, a local role producing an OAuth scope that the access token was never granted.

**Goal:** design authority mappings per namespace/issuer/profile, eliminate duplicates, and enforce authorization conditions with **AND** when scope, local entitlement, and resource permissions are all required together.

## 2. How Spring Security creates authorities from a JWT

### 2.1. `GrantedAuthority`

Spring Security uses the interface:

~~~java
org.springframework.security.core.GrantedAuthority
~~~

Common implementation:

~~~java
new SimpleGrantedAuthority("SCOPE_orders.read");
new SimpleGrantedAuthority("ROLE_ORDER_VIEWER");
~~~

Rule:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

checks the **exact authority name**; `SCOPE_orders.read.all` or `ROLE_ORDER_VIEWER` is not automatically equivalent.

### 2.2. Default `JwtGrantedAuthoritiesConverter`

With a JWT Resource Server:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

`JwtGrantedAuthoritiesConverter` typically reads the `scope` or `scp` claim per profile and prepends `SCOPE_`.

For example:

~~~json
{"scope": "orders.read orders.export"}
~~~

produces:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Custom claims such as `app_roles`, `groups`, and `permissions` do **not automatically** become Spring roles in every configuration. To use these claims, build your own converter and validation.

### 2.3. Where conversion sits in the pipeline

~~~mermaid
flowchart TD
    A["Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder: signature/issuer/audience/time"]
    D --> E{"Is token valid?"}
    E -->|"No"| F["Authentication failure: typically 401"]
    E -->|"Yes"| G["JwtAuthenticationConverter"]
    G --> H["Scope converter and application role converter"]
    H --> I["Merge and deduplicate GrantedAuthority"]
    I --> J["JwtAuthenticationToken in SecurityContext"]
    J --> K["AuthorizationFilter or method security"]
    K --> L["Check endpoint and record permissions"]
~~~

**The converter does not replace validators.** A `roles` claim may only be used as an authority source after the JWT has a valid signature, right issuer/audience, valid timestamps, and passes the claim contract.

## 3. Authority-granting contract and trust boundaries

Before mapping permissions, decide **which source has authority to grant which kind of permission**.

| Data source | Illustrative shape | Permitted to grant | Should not self-grant |
|---|---|---|---|
| JWT `scope` | `orders.read` | `SCOPE_orders.read` | `ROLE_ADMIN` |
| JWT `scp` | `["orders.read"]` | Per issuer profile if selected | Do not blindly add both `scp` and `scope` without agreement |
| JWT `app_roles` | `["ORDER_VIEWER"]` | `ROLE_ORDER_VIEWER` via allowlist | Unfamiliar roles or roles of another API |
| JWT `groups` | `["customer-support"]` | Only per approved mapping | `ROLE_ADMIN` from a group name containing `admin` |
| Database entitlement | `CAN_APPROVE_ORDER` | Current authorization condition | Do not create an OAuth approve scope |
| Tenant/ACL | `tenant-42` / owner | Object scope allowed for read/write | Global role across all tenants |
| HTTP request header | `X-Roles: ADMIN` | Grant no authorities | Do not trust as proof |
| Query/body input | `role=admin` | Grant no authorities | Do not mutate Authentication to open access |

Example contract for Orders API:

~~~text
Trusted issuer:
  https://id.example.test/realms/shop

Required audience:
  orders-api

Scope:
  scope claim is a space-separated String
  recognized scopes: orders.read, orders.write, orders.export

Application role:
  app_roles claim is an optional Array<String>
  allowlist: ORDER_VIEWER, ORDER_EDITOR

Output:
  SCOPE_<scope>
  ROLE_<app_role>

Do not auto-convert:
  groups -> roles
  tenant_id -> global role
  database entitlement -> OAuth scope
~~~

**Both issuer and audience must be checked.** A validly signed JWT from the same IdP issued for `billing-api` must not be used to create Orders API authorities. With multiple issuers, do not apply the same role mapping if role meanings differ by issuer.

## 4. Three operations: union, deduplication, and AND

### 4.1. Union: combining two authority-granting sources

Suppose:

~~~text
Scopes A = {SCOPE_orders.read, SCOPE_orders.export}
Roles  B = {ROLE_ORDER_VIEWER, ROLE_ORDER_EDITOR}
~~~

Union result:

~~~text
A ∪ B = {
  SCOPE_orders.read,
  SCOPE_orders.export,
  ROLE_ORDER_VIEWER,
  ROLE_ORDER_EDITOR
}
~~~

Union is appropriate **when both A and B are approved sources for granting their respective authorities**. Because it is additive, trust and policy must be verified.

### 4.2. Deduplication: removing duplicate entries

~~~text
Input:
  SCOPE_orders.read
  SCOPE_orders.read
  ROLE_ORDER_VIEWER
  ROLE_ORDER_VIEWER

Output:
  SCOPE_orders.read
  ROLE_ORDER_VIEWER
~~~

Deduplication keeps the permission set consistent for logs, tests, and custom code. However, **deduplication does not protect against escalation**: if an untrusted source injects `ROLE_SUPER_ADMIN`, a `Set` still retains one copy of that admin privilege.

### 4.3. AND: multiple sources must all permit the action

A user may have a local permission to approve orders, yet the current token was issued to an OAuth client with only `orders.read`. If the application allows approval based solely on the local permission, it exceeds the token's scope.

A safe API rule requires both:

~~~text
ALLOW_APPROVE_ORDER =
    valid JWT
    AND has SCOPE_orders.approve
    AND local entitlement APPROVE is active
    AND tenant/ownership policy allows order
~~~

Do not use:

~~~text
ALLOW_APPROVE_ORDER =
    has SCOPE_orders.approve
    OR local entitlement APPROVE
~~~

**"Intersecting permissions" between scope and entitlement is usually a logical AND of conditions**, not necessarily string-set intersection, because the two sources use different namespaces.

Wrong example when AND is needed:

~~~java
.hasAnyAuthority(
    "SCOPE_orders.approve",
    "PERM_ORDER_APPROVE"
)
~~~

`hasAnyAuthority` checks **OR**. You must define AND through an authorization manager or method security if both are mandatory.

## 5. Distinguishing `SCOPE_`, `ROLE_`, and `PERM_` namespaces

The strings:

~~~text
SCOPE_admin
ROLE_ADMIN
PERM_ADMIN
~~~

are not identical and carry no implicit equivalence. Do not strip all prefixes to merge them into a single `ADMIN`.

- `SCOPE_`: OAuth scope granted to the token.
- `ROLE_`: application role mapped from an authorized source.
- `PERM_`: internal permission if deliberately defined by the application.

Use `hasAuthority("ROLE_ORDER_VIEWER")` for exact matching. Under the default role prefix, `hasRole("ORDER_VIEWER")` typically requires `ROLE_ORDER_VIEWER`; avoid writing `hasRole("ROLE_ORDER_VIEWER")` as if Spring will not prepend the prefix.

Never use `contains("ADMIN")` or `contains("orders.read")` on a larger string to grant access. Values like `READ_ONLY_ADMIN_VIEW` and `orders.read.all` contain those substrings without representing the intended permission.

**Case sensitivity:** `ROLE_ORDER_VIEWER` is not implicitly equal to `ROLE_order_viewer`. Maintain a canonical role contract instead of automatically uppercasing or stripping prefixes from every permission source.

## 6. Deduplicating authorities with `LinkedHashSet`

A simple approach:

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;

public final class AuthorityCombiner {

    private AuthorityCombiner() {}

    public static List<GrantedAuthority> unique(
            Collection<? extends GrantedAuthority> left,
            Collection<? extends GrantedAuthority> right) {

        LinkedHashSet<GrantedAuthority> result =
            new LinkedHashSet<>();

        result.addAll(left);
        result.addAll(right);

        return List.copyOf(result);
    }
}
~~~

`LinkedHashSet` removes duplicates using `equals`/`hashCode` and preserves insertion order. With `SimpleGrantedAuthority`, equality is based on the authority string.

If a custom `GrantedAuthority` implementation has different `equals`/`hashCode`, decide whether "duplicate" is by object or by **`getAuthority()`**. You can use `LinkedHashMap<String, GrantedAuthority>` to deduplicate by name:

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class AuthorityNameCombiner {

    private AuthorityNameCombiner() {}

    public static List<GrantedAuthority> uniqueByName(
            Collection<? extends GrantedAuthority> input) {

        Map<String, GrantedAuthority> byName = new LinkedHashMap<>();

        for (GrantedAuthority value : input) {
            if (value == null) {
                continue;
            }
            String name = value.getAuthority();
            if (name == null || name.isBlank()) {
                continue;
            }

            byName.putIfAbsent(
                name, new SimpleGrantedAuthority(name));
        }

        return List.copyOf(byName.values());
    }
}
~~~

**Run this only after each source has been verified and mapped per contract.** Never turn deduplication into a place that "fixes" untrusted names into higher-privilege authorities.

## 7. Converter combining scopes and allowlisted app roles

Suppose the issuer emits `app_roles` with recognized values:

~~~text
ORDER_VIEWER
ORDER_EDITOR
~~~

Only these two values are mapped to:

~~~text
ROLE_ORDER_VIEWER
ROLE_ORDER_EDITOR
~~~

### 7.1. Configuring `JwtAuthenticationConverter`

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthorityMappingConfig {

    private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_VIEWER", "ORDER_EDITOR");

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        // Issuer contract uses a String-typed "scope" claim.
        scopeConverter.setAuthoritiesClaimName("scope");
        scopeConverter.setAuthorityPrefix("SCOPE_");

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            LinkedHashSet<GrantedAuthority> authorities =
                new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                scopeConverter.convert(jwt);

            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object raw = jwt.getClaims().get("app_roles");

            if (raw instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if (item instanceof String role
                            && ALLOWED_ROLES.contains(role)) {
                        authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }

            return List.copyOf(authorities);
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }
}
~~~

With the token:

~~~json
{
  "scope": "orders.read orders.read orders.export",
  "app_roles": ["ORDER_VIEWER", "ORDER_VIEWER"]
}
~~~

the result should be:

~~~text
SCOPE_orders.read
SCOPE_orders.export
ROLE_ORDER_VIEWER
~~~

**Why does this limit escalation?**

- `scope` is only converted into the `SCOPE_` namespace.
- `app_roles` only generates `ROLE_...` after matching the **allowlist**.
- It does not automatically read `groups` or arbitrary custom claims.
- It does not create `SCOPE_orders.write` just because the user has an editor role; the token's scope remains the source of truth for OAuth scopes.
- `LinkedHashSet` deduplicates entries.
- It does not accept `SUPER_ADMIN` because it is outside the contract.

This **is not enough for complete security**: the JWT still must pass signature, issuer, audience, and claim validators before mapping, and authorization must still check scope/entitlement/tenant.

### 7.2. How should wrong-typed role claims be handled?

The converter above simply ignores invalid values and grants no extra permissions. However, if the contract specifies that `app_roles`, when present, must be an `Array<String>` within the allowlist, **reject the token in a `JwtDecoder` validator**. Do not let an issuer emitting a broken schema pass silently, especially when other claims affect permissions.

For example:

~~~json
{"app_roles": "ORDER_VIEWER"}
~~~

or:

~~~json
{"app_roles": ["ORDER_VIEWER", 42]}
~~~

both violate the `Array<String>` contract. Do not coerce a String into an array or a Number into a role.

## 8. Wiring the converter into the Resource Server

Dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

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

`issuer-uri` and `audiences` must match the real Authorization Server/API; the audience property is available in Spring Boot versions that support it. Values here are illustrative.

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)
                )
            );

        return http.build();
    }
}
~~~

When multiple converter/decoder beans exist, use explicit wiring or `@Qualifier`. The chain above only matches `/api/**`; production applications must protect other paths with appropriate chains.

Customizing `JwtAuthenticationConverter` **does not automatically alter JWT validation**. If you define a custom `JwtDecoder` bean yourself, Spring Boot may stop auto-configuring the decoder, and the application must explicitly keep issuer/time/audience/token-profile validators.

## 9. `DelegatingJwtGrantedAuthoritiesConverter`: built-in composition

Spring Security also provides **`DelegatingJwtGrantedAuthoritiesConverter`** to run multiple converters and aggregate authorities, with deduplication during combination.

Structural example:

~~~java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();

scopes.setAuthoritiesClaimName("scope");
scopes.setAuthorityPrefix("SCOPE_");

Converter<Jwt, Collection<GrantedAuthority>> appRoles =
    jwt -> trustedAppRoleAuthorities(jwt);

DelegatingJwtGrantedAuthoritiesConverter combined =
    new DelegatingJwtGrantedAuthoritiesConverter(scopes, appRoles);

JwtAuthenticationConverter authConverter =
    new JwtAuthenticationConverter();

authConverter.setJwtGrantedAuthoritiesConverter(combined);
~~~

Imports:

~~~java
import java.util.Collection;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
~~~

`trustedAppRoleAuthorities(jwt)` is a helper **the application must implement itself**, applying an allowlist like section 7; it is not a built-in Spring method. Section 7 shows a complete implementation without needing this helper.

Delegation works well when each source has its own converter. However, it only **merges authorities**; it does not know which source is permitted to grant which privilege, does not validate role schemas, and **does not turn a union into an AND condition**. Keep trust policies/validators and authorization rules in place.

## 10. Validating custom role claims when defining a custom JwtDecoder

To reject JWTs whose `app_roles` has the wrong type or falls outside the allowlist, attach an `OAuth2TokenValidator<Jwt>`. Example:

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.Set;

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

    private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_VIEWER", "ORDER_EDITOR");

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return invalid("Token audience is not orders-api");
        };

        OAuth2TokenValidator<Jwt> appRolesSchema = jwt -> {
            Object raw = jwt.getClaims().get("app_roles");

            if (raw == null) {
                return OAuth2TokenValidatorResult.success();
            }

            if (!(raw instanceof Collection<?> roles)
                    || roles.size() > 20) {
                return invalid("Invalid app_roles type or size");
            }

            for (Object value : roles) {
                if (!(value instanceof String role)
                        || !ALLOWED_ROLES.contains(role)) {
                    return invalid("Unknown app role");
                }
            }

            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience,
                appRolesSchema
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

Meaning:

1. `NimbusJwtDecoder` verifies the signature using a trusted public key.
2. `JwtValidators.createDefaultWithIssuer(ISSUER)` enforces the issuer and basic timestamp checks.
3. The audience validator rejects access tokens intended for other APIs.
4. The custom role validator rejects `app_roles` claims that violate the contract.
5. The converter maps only roles inside the allowlist.

**The converter layer receives a `Jwt` after claim conversion.** If the profile requires strict JSON wire types for registered claims such as `aud`/`exp`, additional control over the claim-set converter/parser may be needed; never skip signature verification to inspect raw JSON data directly.

**Bean override note:** when defining a custom `JwtDecoder`, convenient Boot properties no longer automatically attach to this decoder. Do not lose issuer, expiration, audience, token type, and custom claim validations. `setJwtValidator(...)` replaces the configured validator, so compose all of them together.

## 11. Local entitlements must not self-grant extra OAuth scopes

A user may have an internal `APPROVE_ORDER` permission in the database, while the current access token only has:

~~~json
{"scope": "orders.read"}
~~~

If the converter queries the DB and adds `SCOPE_orders.approve` for the user, the token has been **escalated beyond its granted scope**. If the endpoint uses `hasAnyAuthority("SCOPE_orders.approve", "PERM_ORDER_APPROVE")`, the local permission can unlock approval even though the token lacks the scope.

When the contract requires both conditions, express it as:

~~~text
ALLOW_APPROVE =
    JWT has SCOPE_orders.approve
    AND user has active APPROVE entitlement
    AND current order policy allows action
~~~

Do not conflate:

- **Token scope:** which action type the client/token is authorized to request.
- **User entitlement:** what the organization currently permits the user/service to do.
- **Resource ownership/ACL:** whether the caller may perform the action on the specific record.

All three protection layers may need to pass simultaneously. Never simply union three sources and check them with an OR rule.

## 12. Method security using AND with live entitlements

To avoid pushing all local permissions into `JwtAuthenticationConverter`, you can check them in the service layer.

Enable method security:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {}
~~~

Service:

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrdersService {

    private final OrderRepository repository;

    public OrdersService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @ordersPolicy.canRead(authentication, #orderId)"
    )
    public OrderDto loadOrder(long orderId) {
        return repository.findOrderDto(orderId);
    }
}
~~~

Policy:

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component("ordersPolicy")
public class OrdersPolicy {

    private final OrderAccessRepository access;

    public OrdersPolicy(OrderAccessRepository access) {
        this.access = access;
    }

    public boolean canRead(Authentication authentication, long orderId) {
        if (authentication == null
                || !(authentication.getPrincipal() instanceof Jwt jwt)) {
            return false;
        }

        Object raw = jwt.getClaims().get("tenant_id");
        String subject = jwt.getSubject();

        if (!(raw instanceof String tenant)
                || tenant.isBlank()
                || subject == null
                || subject.isBlank()) {
            return false;
        }

        // Verify permission is still active and object belongs to the right tenant.
        return access.canReadOrder(subject, tenant, orderId);
    }
}
~~~

`OrderRepository`, `OrderAccessRepository`, `OrderDto`, and `canReadOrder` are illustrative domain components that you implement. Real queries must combine tenant, owner/ACL, entitlement, and appropriate business status.

In this flow:

1. The token must be valid to build `Authentication`.
2. `@PreAuthorize` requires `SCOPE_orders.read`.
3. The policy checks live entitlement at request time and the order's tenant.
4. Any condition failing → reject.
5. Never use client queries/headers as proof of having an authority.

With proxy-based method security, remember **self-invocation** can bypass advice. SpEL `#orderId` also requires parameter names to be resolvable (e.g., `-parameters` compiler flag in Java depending on setup). Test these boundaries in practice.

If the database/policy service fails, **never return true by default**. Infrastructure failures may surface as service errors, but must never grant access.

## 13. Tenants and multi-issuer setups make the problem harder

### 13.1. Roles are not automatically global across all tenants

A token:

~~~json
{
  "scope": "orders.read",
  "app_roles": ["ORDER_VIEWER"],
  "tenant_id": "tenant-42"
}
~~~

does not mean the caller can view orders belonging to `tenant-99`. Even with `ROLE_ORDER_VIEWER`, the API must check permission against the request's **tenant/resource**.

If an issuer emits per-tenant roles, do not union all tenant roles into global authorities. There must be rules selecting the valid tenant and checking the corresponding resource scope.

### 13.2. Issuer A's role does not automatically equal Issuer B's role

Issuer A has `roles: ["EDITOR"]` and Issuer B also has `roles: ["EDITOR"]`, yet system permissions differ. If the Resource Server trusts multiple issuers, there should not be one shared converter turning every `EDITOR` into `ROLE_ORDER_EDITOR`.

You need:

- An allowlist of trusted issuers.
- JWT verification using the right issuer's keys/validators.
- Audience check for `orders-api`.
- Role mapping per **issuer-specific policy**.
- Local entitlement and tenant/ownership checks if needed.

`JwtIssuerAuthenticationManagerResolver` is a Servlet Resource Server extension point for multi-issuer scenarios. The initial `iss` claim is only an **unverified routing hint**; never allow loading metadata/keys from arbitrary issuers advertised by a token.

## 14. Dynamic permissions and revocation

A JWT access token can remain valid after a user's role is revoked in the system. If all permissions are baked into the JWT at issuance time, the Resource Server does not automatically know about newer entitlement changes.

Consider based on action sensitivity:

- Shorten access token lifetimes.
- Check current local permissions for critical endpoints.
- Use token introspection/denylist/revocation if supported by the architecture.
- Cache entitlements with appropriate TTL/invalidation.
- Check ownership/tenant at object-processing time.

**JWKS caching is not user-permission caching.** JWKS stores public keys to verify JWTs. Caching local entitlements or authorization decisions is a separate design that risks extending revoked permissions if misconfigured.

## 15. Testing to detect unintended privilege escalation

### 15.1. Converter matrix

| JWT claims | Expected result |
|---|---|
| `scope: "orders.read"` | `SCOPE_orders.read` |
| `scope: "orders.read orders.read"` | Single `SCOPE_orders.read` |
| `app_roles: ["ORDER_VIEWER"]` | `ROLE_ORDER_VIEWER` |
| `app_roles: ["ORDER_VIEWER", "ORDER_VIEWER"]` | Single `ROLE_ORDER_VIEWER` |
| No `app_roles` | No roles added |
| `app_roles: "ORDER_VIEWER"` | Schema violation; validator rejects |
| `app_roles: [42]` | Schema violation; validator rejects |
| `app_roles: ["SUPER_ADMIN"]` | Does not grant admin; validator rejects |
| `groups: ["admins"]` | Does not create `ROLE_ADMIN` |
| Valid `scope` and `app_roles` | One copy of each authority, namespaces preserved |
| Valid issuer token with different audience | Rejected before authority mapping |
| Client `X-Roles: ADMIN` header | No effect on authorities |

### 15.2. AND matrix

| Has `orders.read` scope? | Local entitlement + tenant allow? | Result |
|---|---|---|
| No | No | Deny |
| No | Yes | Deny |
| Yes | No | Deny |
| Yes | Yes | Allow |

If the "no scope, has DB permission" row is allowed, the policy has accidentally turned AND into OR.

### 15.3. MockMvc rule testing differs from converter testing

Spring Security Test has a helper:

~~~java
mockMvc.perform(
    get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"),
            new SimpleGrantedAuthority("ROLE_ORDER_VIEWER")
        ))
);
~~~

This simulates an `Authentication` that already has authorities to test authorization. It **does not prove** that the custom converter read claims accurately or that the JWT decoder verified signature/issuer/audience.

There should be three test layers:

1. **Converter tests:** construct a `Jwt` with claims and verify the resulting authority set is accurate, deduplicated, and free of unknown roles.
2. **Validator tests:** wrong types/unknown roles, wrong issuer/audience, tokens missing mandatory claims.
3. **Integration tests:** send signed test Bearer JWTs through the real Resource Server, checking 401/403, scope + local entitlement + tenant/ACL.

Never edit a real token's payload and conclude a custom role validator works; altering the JWT payload usually breaks the signature before reaching the validator.

## 16. Common misconceptions

### 16.1. "Using a `Set` prevents privilege escalation"

False. `Set` only removes duplicates. A `ROLE_ADMIN` privilege from an untrusted source is still dangerous even if it appears only once.

### 16.2. "Group, role, and scope are just different names for the same thing"

False. They have different sources, meanings, and scopes; map them only per a specific contract.

### 16.3. "If the database has the permission, the access token implicitly has the matching scope"

False. Local entitlements do not automatically expand OAuth scopes. If both are needed, use AND.

### 16.4. "Any role containing the word admin is an admin"

False. Do not match by substring; use exact roles in an allowlist. Never map a group named `admins` into `ROLE_ADMIN` automatically.

### 16.5. "All roles can have their prefixes stripped and normalized"

Never strip `ROLE_` or alter casing arbitrarily. The contract must state exact role values and which authorities the converter produces.

### 16.6. "One converter works for every issuer"

Dangerous when issuers have different role semantics. You need per-issuer mapping, a trusted allowlist, and the right audience.

### 16.7. "Having read authority lets you view every record"

False. Endpoint authorization still requires tenant/owner/ACL checks on the resource.

### 16.8. "Long-lived caching of local permissions causes no issues"

If permissions are revoked while caches remain uninvalidated, callers can continue gaining access. Define revocation latency bounds explicitly and fail closed when policy cannot be verified.

## 17. Summary diagram

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Verify JWT: signature + iss + aud + expiry"]
    B --> C{"Valid?"}
    C -->|No| X["401"]
    C -->|Yes| D["Trusted scopes -> SCOPE_*"]
    C --> E["Validated app_roles allowlist -> ROLE_*"]
    D --> F["Controlled union + dedup"]
    E --> F
    F --> G["Authentication in SecurityContext"]
    G --> H{"Has scope for action?"}
    H -->|No| Y["403"]
    H -->|Yes| I{"Live local entitlement?"}
    I -->|No| Y
    I -->|Yes| J{"Valid tenant/owner/ACL?"}
    J -->|No| Y
    J -->|Yes| K["Allow operation"]
~~~

**Conclusion:** combining authorities involves **identifying trusted sources**, **mapping per contract**, **deduplicating**, and then **enforcing independent policies**. Never treat union as a replacement for all permission conditions. OAuth scopes constrain which actions the client is delegated to perform, while local entitlements and tenant/ownership constrain permissions on the data itself. For endpoints needing all three, use **AND**, never OR.

### References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html)
- [Spring Security API — DelegatingJwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DelegatingJwtGrantedAuthoritiesConverter.html)
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html)
- [Spring Security API — GrantedAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/GrantedAuthority.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
