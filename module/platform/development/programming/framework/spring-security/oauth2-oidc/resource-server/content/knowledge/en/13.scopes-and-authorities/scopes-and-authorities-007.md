# Nested Roles, Permissions in Tokens, and Contract-Based Converters

When implementing a **Spring Security OAuth 2.0 / OIDC Resource Server**, a JWT access token does not necessarily place all permissions in the `scope` claim. Many identity systems also put **roles** or **permissions** inside nested JSON objects, such as `realm_access.roles`, `resource_access.orders-api.roles`, or `authorization.permissions[].scopes`. For an API to use these values in `hasAuthority(...)` or `@PreAuthorize`, it needs a **converter** that understands the exact token format and turns verified claims into `GrantedAuthority` objects according to **the application's permission contract**.

The most important point is: **Spring Security cannot automatically know what an issuer's "admin" role or a "read" permission inside an object means for the Orders API**. Being able to read a JSON field does not mean that field is trustworthy, belongs to the right API, or is authorized to grant an equivalent internal privilege.

> **Rule:** Verify the JWT first; confirm issuer, audience, and token profile; read only agreed claim paths; map only **permitted values** into clearly named authorities; and finally still check scopes and policies against the real resource. Never use a nested role array in a token to "automatically grant all privileges".

## 1. Problem: Why is `scope` alone not enough?

Suppose a commerce system has:

- **Identity Server** acting as the Authorization Server, issuing signed JWT access tokens.
- **Shop Web** as the OAuth2 Client requesting access tokens.
- **Orders API** as the Spring Security Resource Server, accepting only tokens whose `aud` matches `orders-api`.
- **Order database** storing owner, tenant, order status, and assigned group.

When Shop Web calls:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

The Orders API may need to verify all three conditions:

1. **The access token** has the `orders.read` scope allowing an attempt to call the read endpoint.
2. The caller has the **permission** `order:read:own` or `order:read:tenant`, which may be represented in a nested claim.
3. Order record 42 is in a tenant, belongs to an owner, or is assigned to a group permitted by data and business policies.

By default, Spring Security typically converts `scope: "orders.read"` into the `SCOPE_orders.read` authority, but **does not automatically derive** `ROLE_ORDER_SUPPORT` from `resource_access.orders-api.roles`, nor does it create `PERM_order:read:tenant` from a custom `authorization.permissions` object.

Therefore, you need to design a converter with clear roles and boundaries:

~~~mermaid
flowchart TD
    A["Bearer JWT"]
    B["JwtDecoder: verify signature and claims"]
    C["Is JWT valid for iss/aud/exp?"]
    D["JwtAuthenticationConverter"]
    E["Scope: scope/scp"]
    F["Roles: nested resource_access"]
    G["Permissions: nested authorization"]
    H["GrantedAuthorities with clear namespaces"]
    I["HTTP/method authorization"]
    J["Owner, tenant, status policy"]
    X["Reject authentication"]

    A --> B --> C
    C -->|No| X
    C -->|Yes| D
    D --> E
    D --> F
    D --> G
    E --> H
    F --> H
    G --> H
    H --> I --> J
~~~

Representing permissions in a token is only **an input to the authorization decision**, not a substitute for decisions on the data object itself.

## 2. Distinguishing scope, role, permission, and GrantedAuthority

| Concept | Question it answers | Example | Who defines / uses it? |
| --- | --- | --- | --- |
| **OAuth2 scope** | Which access range was granted to the token? | `orders.read`, `orders.cancel` | AS issues per Client/grant policy; API specifies endpoints |
| **Role** | What role does the Subject hold in a permission domain? | `order_support`, `tenant_admin` | Identity/authorization domain; often mapped to RBAC |
| **Permission** | What specific capability does the Subject have? | `order:read:tenant`, `order:cancel:own` | System permission policy; may come from a role or direct grant |
| **GrantedAuthority** | Which permission string does Spring Security match? | `SCOPE_orders.read`, `ROLE_ORDER_SUPPORT`, `PERM_order:read:tenant` | Resource Server creates via converter and/or internal permission source |
| **Resource policy** | May the Subject act on a specific record? | Only read orders of assigned tenant | API/business layer applies trusted data |

These concepts may relate to one another, but they are not identical:

- **Scope** usually constrains the **API entry gate**: may this token call this capability?
- **Role** groups permissions by responsibility: support agent, tenant admin, etc.
- **Permission** describes a fine-grained action: read own orders, view tenant orders, etc.
- **Authority** is the representation **inside Spring Security**, usually a string.
- **Data policy** uses owner/tenant/status to decide specific cases.

The JWT specification does not require every token to carry `roles` or `permissions`. OAuth 2.0 does not standardize the role `ORDER_SUPPORT` or the permission `order:read:tenant`. Those names must be **agreed upon between the Authorization Server and the Resource Server**, documented, and versioned when changed.

### 2.1. Authority names must match exactly

With the default converter, the claim:

~~~json
{"scope": "orders.read orders.cancel"}
~~~

can be mapped to:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Thus:

~~~java
hasAuthority("SCOPE_orders.read")
~~~

is different from:

~~~java
hasAuthority("orders.read")
~~~

Similarly, `hasRole("ORDER_SUPPORT")` under prefix conventions typically checks the `ROLE_ORDER_SUPPORT` authority. If the converter creates `ROLE_ORDER_SUPPORT`, you can use `hasRole("ORDER_SUPPORT")` or `hasAuthority("ROLE_ORDER_SUPPORT")` per the chosen convention. The `PERM_` prefix in the examples below **is an application-defined convention**, not a Spring Security default.

## 3. What does "nested in the token" mean?

Here, **nested roles/permissions** means JSON claims containing nested objects or lists. It is **not synonymous** with a JOSE *nested JWT* (a JWS inside a JWE). We are referring to the shape of the **JWT Claims Set** after the token has been verified.

### 3.1. Roles in a top-level claim

Simple format:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["order_support", "tenant_admin"]
}
~~~

The Resource Server can read `roles` as a list of strings. However, this claim might hold organization-wide roles or roles for another Client if the contract is not explicit. **Never automatically assume that every value in `roles` applies to the Orders API**.

### 3.2. Roles nested by realm and by resource/client

Some Identity Providers—such as the pattern commonly seen in Keycloak—may use claims like:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "realm_access": {
    "roles": ["platform_auditor", "default-roles-shop"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["order_support"]
    },
    "billing-api": {
      "roles": ["billing_admin"]
    }
  }
}
~~~

The two paths have different semantics:

| Path | Information represented | How Orders API should handle it |
| --- | --- | --- |
| `realm_access.roles` | Realm/identity-domain level roles | Use only if a contract defines which roles pertain to Orders API |
| `resource_access["orders-api"].roles` | Roles tied to the resource/client named `orders-api` per issuer | May map roles permitted by Orders API |
| `resource_access["billing-api"].roles` | Roles intended for another resource/client | **Do not** convert into Orders API admin authorities |
| `scope` | OAuth2 scopes of the access token | Map according to the agreed scope rules |

In many identity products, **Client ID**, **resource identifier**, and **JWT audience** can be completely different values. For example, `resource_access["orders-api"]` uses the Client ID key of an application registered in the IdP, whereas `aud` might be a resource URI. This lesson uses matching strings for clarity; real implementations must document each value explicitly in the contract and **never infer the `resource_access` key from a hostname or an `aud` element**.

### 3.3. Permissions can be multi-level nested objects and lists

Example of a **system-defined** contract:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-A",
  "authorization": {
    "permissions": [
      {
        "resource": "orders",
        "scopes": ["read:tenant", "comment:tenant"]
      },
      {
        "resource": "reports",
        "scopes": ["export"]
      }
    ]
  }
}
~~~

In this example:

- `authorization` is an object.
- `authorization.permissions` is an array of objects.
- Each permission has a `resource` and a `scopes` array **belonging to the resource's permission**.
- `authorization.permissions[0].scopes` **is not the same as** the top-level OAuth2 `scope` claim.

The names `resource` and `scopes` inside `authorization.permissions` are only an **illustrative contract**, not a universal standard format for all JWT access tokens. A Keycloak Authorization Services system might use an `authorization.permissions` structure containing fields like `rsid`, `rsname`, and `scopes`; another issuer might use URI claims or entirely different JSON. **Never copy a converter from product A to product B without checking real tokens and the issuer's documentation.**

## 4. The claim contract must be written clearly before coding

Taking Orders API as an example, we agree on:

| Contract element | Example value/format | Trust rule |
| --- | --- | --- |
| **Issuer** | `https://id.example.test/realms/shop` | Must match trusted issuer with valid signature |
| **Audience** | Contains `orders-api` | Token must be intended for Orders API |
| **Token type** | OAuth2 JWT access token | Do not accept an OIDC ID token as an access token |
| **Scope** | `scope` is a space-delimited string or per supported profile | Spring converts to `SCOPE_...` |
| **Realm roles** | `realm_access.roles` is a string array | Accept only roles with explicit mapping |
| **API role lookup** | `resource_access["orders-api"].roles` | Extract only from the registered resource/client |
| **Permission lookup** | `authorization.permissions[]` with `resource` and `scopes[]` | Accept only resource/action pairs in the mapping table |
| **Tenant** | `tenant_id` is a string | Use in policy only after token verification; still verify against resource |
| **User identity** | `(iss, sub)` | Do not use username/email as default authorization key |
| **Spring authority prefixes** | `SCOPE_`, `ROLE_`, `PERM_` | Normalized names used inside the API itself |

### 4.1. Explicit mapping table

For example, the business decides:

| Token source | Received value | Generated authority | Meaning in API |
| --- | --- | --- | --- |
| OAuth2 scope | `orders.read` | `SCOPE_orders.read` | Permitted to request read operations |
| OAuth2 scope | `orders.cancel` | `SCOPE_orders.cancel` | Permitted to request cancel operations |
| Realm role | `platform_auditor` | `ROLE_PLATFORM_AUDITOR` | Auditor role approved by the system |
| `orders-api` role | `order_support` | `ROLE_ORDER_SUPPORT` | Support staff within defined boundaries |
| `orders-api` role | `tenant_admin` | `ROLE_TENANT_ADMIN` | Admin for the authorized tenant |
| `orders` permission scope | `read:own` | `PERM_order:read:own` | May read orders owned by the principal |
| `orders` permission scope | `read:tenant` | `PERM_order:read:tenant` | May read orders within the permitted tenant |
| `orders` permission scope | `cancel:own` | `PERM_order:cancel:own` | May cancel own order when status allows |

Do not map `billing_admin` inside `resource_access["billing-api"]` to `ROLE_TENANT_ADMIN` of Orders API. Do not map disallowed roles like `default-roles-shop` to application authorities. If the issuer adds a new role, the Resource Server **does not automatically grant the new privilege** unless the mapping contract is intentionally updated.

### 4.2. Distinguishing assigned roles from derived permissions

An issuer may emit both roles and permissions. In that case, you must know:

- Are roles and permissions **two independent sources**, or are permissions computed from roles?
- Are **both scope and permission** required, or only one of the two?
- If a token has a role yet lacks the corresponding permission, how should the API respond?
- **Within which tenant** does the role take effect?
- Were the permissions checked against current entitlements by the issuer, or could they be stale?

In this lesson, the converter **only converts claim data into authorities**. It **does not automatically expand** `ROLE_ORDER_SUPPORT` into `PERM_order:read:tenant`. If the system has a role → permission rule, implement it in **one clear place** via a dedicated policy/authorization component, or let the Authorization Server emit pre-computed permissions per contract. Avoid computing them in multiple places simultaneously, which leads to conflicting privilege grants.

## 5. Standard processing flow in Spring Security

The proper flow is:

~~~text
HTTP request + Bearer access token
    |
    v
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder / NimbusJwtDecoder
  - verify JWS signature using trusted public key/JWKS
  - validate iss, exp, nbf, aud, token profile per configuration
    |
    v
JwtAuthenticationConverter
  - extract SCOPE_ from scope/scp
  - read realm_access.roles per mapping
  - read resource_access["orders-api"].roles per mapping
  - read authorization.permissions per mapping
    |
    v
JwtAuthenticationToken
  - principal: verified Jwt
  - authorities: internal permission set
    |
    v
SecurityFilterChain / @PreAuthorize
    |
    v
Service policy: tenant, owner, resource status
~~~

**Never write code that parses a raw JWT and builds authorities outside `JwtDecoder`.** A sender can craft a payload containing `"roles": ["tenant_admin"]` themselves. If the token is unverified and the converter still trusts that field, the API lets callers grant themselves permissions.

### 5.1. How does Spring Security convert scopes by default?

Spring Security's `JwtGrantedAuthoritiesConverter` supports mapping scopes from common claims `scope` or `scp` in supported formats. Example:

~~~json
{
  "sub": "user-842",
  "scope": "orders.read orders.cancel"
}
~~~

Typical authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

However, this default behavior does not mean it automatically reads:

~~~text
realm_access.roles
resource_access.orders-api.roles
authorization.permissions[*].scopes
~~~

**A nested claim is structured JSON data, not a top-level claim name containing dots.** Calling `setAuthoritiesClaimName("resource_access.orders-api.roles")` is not a generic way to traverse objects like JSONPath; you must write a converter that actually reads the nested structure.

## 6. Implementing `JwtAuthenticationConverter` for nested roles and permissions

The example below targets **Spring Boot 3 / Spring Security 6 on Java 17+**. The Java code implements a concrete, intentional contract:

- Preserves the default scope mapping.
- Extracts only the `platform_auditor` realm role.
- Extracts roles only from `resource_access["orders-api"]`, not from `billing-api`.
- Extracts permissions only for the `orders` resource, with allowed actions.
- Deduplicates authorities using `LinkedHashSet`.
- Ignores missing or structurally mismatched optional claims; if a claim is mandatory, use a **validator to reject the token** per contract (section 8).

### 6.1. Dependencies and configuration

~~~groovy
dependencies {
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
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
    resource-client-id: orders-api
~~~

Keeping **expected-audience** and **resource-client-id** separate is intentional. In the example both may be `orders-api`; in another IdP, the `resource_access` key may not match the audience. URLs, issuer, JWKS, and audience for each environment must come from the trusted issuer rather than guesswork.

### 6.2. Complete converter, allowlist-based mapping

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
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

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter(
            @Value("${app.security.resource-client-id}") String resourceClientId) {

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("sub");
        converter.setJwtGrantedAuthoritiesConverter(
                new NestedAuthoritiesConverter(resourceClientId));
        return converter;
    }

    static final class NestedAuthoritiesConverter
            implements Converter<Jwt, Collection<GrantedAuthority>> {

        private static final Map<String, String> REALM_ROLES = Map.of(
                "platform_auditor", "ROLE_PLATFORM_AUDITOR");

        private static final Map<String, String> ORDERS_ROLES = Map.of(
                "order_support", "ROLE_ORDER_SUPPORT",
                "tenant_admin", "ROLE_TENANT_ADMIN");

        private static final Map<String, String> ORDER_PERMISSIONS = Map.of(
                "read:own", "PERM_order:read:own",
                "read:tenant", "PERM_order:read:tenant",
                "cancel:own", "PERM_order:cancel:own");

        private final String resourceClientId;
        private final JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        NestedAuthoritiesConverter(String resourceClientId) {
            this.resourceClientId = resourceClientId;
        }

        @Override
        public Collection<GrantedAuthority> convert(Jwt jwt) {
            Set<GrantedAuthority> result = new LinkedHashSet<>();

            // 1) OAuth 2.0 scope: keep default SCOPE_...
            Collection<GrantedAuthority> scopeAuthorities =
                    scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            // 2) Realm roles: accept only values in the allowlist table.
            Map<String, Object> realm = jwt.getClaimAsMap("realm_access");
            if (realm != null) {
                addMappedRoles(result, realm.get("roles"), REALM_ROLES);
            }

            // 3) Resource-specific roles: only from this API's client/resource.
            Map<String, Object> resources =
                    jwt.getClaimAsMap("resource_access");
            if (resources != null) {
                Object currentResource = resources.get(resourceClientId);
                if (currentResource instanceof Map<?, ?> attributes) {
                    addMappedRoles(
                            result, attributes.get("roles"), ORDERS_ROLES);
                }
            }

            // 4) Nested permissions object per Orders API contract.
            Map<String, Object> authorization =
                    jwt.getClaimAsMap("authorization");
            if (authorization != null) {
                Object rawPermissions = authorization.get("permissions");
                if (rawPermissions instanceof Collection<?> permissions) {
                    for (Object item : permissions) {
                        if (!(item instanceof Map<?, ?> permission)) {
                            continue;
                        }
                        // Do not pull permissions for other resources.
                        if (!"orders".equals(permission.get("resource"))) {
                            continue;
                        }
                        Object rawScopes = permission.get("scopes");
                        if (rawScopes instanceof Collection<?> values) {
                            for (Object value : values) {
                                if (value instanceof String action) {
                                    String granted =
                                            ORDER_PERMISSIONS.get(action);
                                    if (granted != null) {
                                        result.add(
                                            new SimpleGrantedAuthority(granted));
                                    }
                                }
                            }
                        }
                    }
                }
            }

            return result;
        }

        private static void addMappedRoles(
                Set<GrantedAuthority> output,
                Object rawRoles,
                Map<String, String> allowedRoles) {

            if (!(rawRoles instanceof Collection<?> values)) {
                return;
            }
            for (Object value : values) {
                if (value instanceof String role) {
                    String authority = allowedRoles.get(role);
                    if (authority != null) {
                        output.add(new SimpleGrantedAuthority(authority));
                    }
                }
            }
        }
    }
}
~~~

### 6.3. Step-by-step converter breakdown

**Step 1 — keep OAuth2 scopes:** 

~~~java
JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();
~~~

`scopes.convert(jwt)` preserves `SCOPE_...` authorities from supported scope claims. If you replace the converter and forget this step, a token carrying `orders.read` will no longer satisfy `hasAuthority("SCOPE_orders.read")`.

**Step 2 — read nested objects with proper type checking:**

~~~java
Map<String, Object> resources = jwt.getClaimAsMap("resource_access");
Object current = resources == null ? null : resources.get("orders-api");
~~~

Real tokens might omit `resource_access`, or it might not be an object. The converter should not cast blindly with `(Map<String,Object>)` on unverified shapes, avoiding hard-to-diagnose exceptions. For **optional** claims, absent/malformed data can yield "no corresponding authority"; for **mandatory** claims, use a validator to reject the token explicitly.

**Step 3 — accept only explicitly declared roles:**

~~~java
Map.of("order_support", "ROLE_ORDER_SUPPORT")
~~~

Avoid doing:

~~~java
// Do not use for roles from issuers without an explicit contract:
new SimpleGrantedAuthority("ROLE_" + roleFromAnyNestedClaim);
~~~

If a token contains `billing_admin` or a new role not yet approved by the API team, automatic string concatenation can turn it into an authority with unintended significance. An allowlist table upholds the rule: **never grant new permissions just because a new role name appeared in a token**.

**Step 4 — resource-specific permissions:**

~~~text
authorization.permissions:
  resource = orders
  scopes = [read:own, read:tenant]

=> PERM_order:read:own
=> PERM_order:read:tenant
~~~

Do not treat `reports/export` as an authority on `orders`. If permissions for other resources are added later, define separate converters/policies per contract.

**Step 5 — no duplicate authorities:** `LinkedHashSet` eliminates duplicates if an authority appears across multiple entries. It does not infer any new permissions.

### 6.4. Result with an illustrative JWT

Given a verified JWT:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "realm_access": {
    "roles": ["platform_auditor", "default-roles-shop"]
  },
  "resource_access": {
    "orders-api": { "roles": ["order_support"] },
    "billing-api": { "roles": ["billing_admin"] }
  },
  "authorization": {
    "permissions": [
      { "resource": "orders",
        "scopes": ["read:tenant", "comment:tenant"] },
      { "resource": "reports",
        "scopes": ["export"] }
    ]
  }
}
~~~

The converter in section 6.2 produces:

~~~text
SCOPE_orders.read
ROLE_PLATFORM_AUDITOR
ROLE_ORDER_SUPPORT
PERM_order:read:tenant
~~~

It **does not** create `ROLE_BILLING_ADMIN`, does not create an authority for `default-roles-shop`, and does not create `PERM_report:export:tenant`. `comment:tenant` is also ignored because it is not in the allowed permissions table. If the system wants to use `comment:tenant`, **both the contract and policy** must be updated intentionally.

## 7. Wiring the converter into SecurityFilterChain

Merely declaring a `JwtAuthenticationConverter` bean does not always mean the API configuration automatically uses it. Wire the converter into the JWT Resource Server protecting the routes:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain ordersApi(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(jwtAuthenticationConverter)))
            .build();
    }
}
~~~

This configures **a REST API using Bearer tokens**, without session cookies for `/api/**`; hence the example has CSRF disabled and stateless sessions. If the application has a web UI/sessions, configure CSRF policies and filter chains accordingly rather than copying this setup across the whole app.

At the HTTP layer, `GET /api/orders/**` only requires `SCOPE_orders.read`. Nested roles and permissions are not automatically checked by that rule. The service layer should enforce fine-grained policies, or HTTP rules can combine requirements per contract.

### 7.1. Requiring both scope and permission

If the contract requires **read scope** and **at least one read permission**:

~~~java
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@EnableMethodSecurity
@Configuration
class MethodSecurityConfiguration {
}
~~~

In the service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrdersQueryService {

    private final OrderRepository orders;

    OrdersQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "(hasAuthority('PERM_order:read:own') or " +
        "hasAuthority('PERM_order:read:tenant')) and " +
        "@orderAccess.canRead(authentication, #id)")
    public OrderDto readOrder(String id) {
        return orders.findDtoById(id)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

`OrderRepository`, `OrderDto`, `OrderNotFoundException`, and the `orderAccess` bean are illustrative business components, not built-in Spring Security classes. The `orderAccess` bean must load trusted data for order 42 (owner, tenant, status, assignment) and match it against the verified caller.

Note: A token with `ROLE_ORDER_SUPPORT` **does not automatically turn into** `PERM_order:read:tenant` in the converter written above. A system that derives permissions from roles must have **one place** executing an explicit role → permission rule. Otherwise, a caller holding the role yet missing the permission will be denied by method security per the example contract.

### 7.2. Restricting by real data

Suppose the JWT has:

~~~json
{
  "sub": "support-12",
  "tenant_id": "tenant-A",
  "scope": "orders.read",
  "authorization": {
    "permissions": [
      { "resource": "orders", "scopes": ["read:tenant"] }
    ]
  }
}
~~~

Even when the token has the `PERM_order:read:tenant` authority, the API still must verify that order 42 belongs to **tenant-A** and that the support agent is assigned if policy requires it. Never take `tenant_id` from a Client-sent query string to skip matching. Role/permission may be a **necessary** condition; per-record access is the **sufficient** condition per concrete policy.

## 8. Verify the JWT before trusting nested roles and permissions

**The converter should only receive a `Jwt` from a verified decoder.** Never manually split the `Authorization` header with `String.split("\\.")`, Base64URL-decode it, and extract `realm_access` or `authorization.permissions` to create `GrantedAuthority` instances.

### 8.1. Keep issuer, expiration, and audience checks

Example configuring a custom JWT decoder to validate audience:

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
class JwtTrustConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "JWT is not intended for this API",
                                null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audience));
        return decoder;
    }
}
~~~

`NimbusJwtDecoder` checks the signature with trusted JWKS keys per configured algorithm; the validator checks issuer/timestamps and audience. Production also requires constraining allowed algorithms, token type/profile, and mandatory issuer claims. **Never replace default validators with a validator that only checks permissions.**

If the JWT's `iss` does not match or `aud` does not contain Orders API, the token must be rejected **before** seemingly valid roles are used. A token signed by another issuer containing `role = admin` grants no permissions in Orders API.

### 8.2. Optional claims vs. mandatory claims

The converter example in section 6 **skips permissions** when an optional nested claim is absent or has the wrong type. This does not mean every malformed payload must be accepted as a valid JWT.

Distinguish clearly:

| Claim policy | Appropriate implementation |
| --- | --- |
| Optional roles claim; if missing, no roles granted | Converter returns zero role authorities |
| Optional permissions claim; if missing, no permissions granted | Converter returns zero permission authorities |
| API requires every access token to carry a `tenant_id` claim | Write an `OAuth2TokenValidator<Jwt>` checking existence, type, and format; reject token if invalid |
| A token profile requires `authorization.permissions` to match a schema | Validator/profile layer validates and rejects malformed tokens before reaching the converter |
| A permission is valid only within the current tenant | Data policy checks tenant/owner, not only in the converter |
| Token comes from another issuer with identically named claims | Reject if issuer is not on the allowlist, or use a dedicated profile/mapping |

Example of a validator requiring `tenant_id` to be a non-blank string:

~~~java
OAuth2TokenValidator<Jwt> tenantRequired = jwt -> {
    Object tenant = jwt.getClaims().get("tenant_id");
    if (tenant instanceof String text && !text.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token",
                    "Required tenant_id is missing or invalid", null));
};
~~~

When adding an extra validator, combine it **together with** timestamp, issuer, audience, and token-profile validators. Never replace them with `tenantRequired` alone.

### 8.3. Tokens from multiple issuers should not share mappings indiscriminately

Two Authorization Servers might both emit:

~~~json
{"realm_access":{"roles":["admin"]}}
~~~

yet `admin` from Issuer A is not synonymous with `admin` from Issuer B. For a Resource Server trusting multiple issuers, each issuer needs matching **keys, audience, algorithms, token profile, and mapping table**. Never funnel JWTs from multiple issuers into a shared converter granting `ROLE_ADMIN` without a cross-domain authorization contract.

## 9. Rules for designing safe converters

### 9.1. Only read claims according to the agreed schema

Wrong ways of reading data:

~~~java
// Wrong if you assume getClaimAsStringList() traverses nested objects:
jwt.getClaimAsStringList("resource_access.orders-api.roles");

// Dangerous if applied to arbitrary objects without a contract:
flattenAllStringsRecursively(jwt.getClaims());
~~~

A generic converter that "scans every string in the token and prepends `ROLE_`" can accidentally pull in scopes, usernames, tenants, roles of other Clients, or unrelated data. Instead, navigate the structure using **explicit field names and resource keys**, then match against an explicit mapping table.

### 9.2. Do not escalate privileges through matching role names

For example, a token contains:

~~~json
{
  "resource_access": {
    "billing-api": { "roles": ["admin"] }
  }
}
~~~

This is a role in the Billing API context. **Orders API must not** turn it into `ROLE_ADMIN` and allow order cancellation. The converter must restrict lookup to the `orders-api` key and define explicitly which roles Orders API accepts.

### 9.3. Keep authority namespaces clear

An application can standardize on:

~~~text
SCOPE_orders.read        -> OAuth2 scope
ROLE_ORDER_SUPPORT      -> role in Orders API
ROLE_PLATFORM_AUDITOR   -> approved realm role
PERM_order:read:tenant  -> specific permission
~~~

Avoid letting `ROLE_ADMIN` be produced simultaneously from:

- Realm admin.
- Orders API resource admin.
- Billing API resource admin.
- Custom permissions containing the string "admin".

If roles with identical names are needed across multiple domains, namespace them in the authority name—e.g., `ROLE_ORDERS_ADMIN` and `ROLE_PLATFORM_ADMIN`—and update `hasAuthority` expressions accordingly.

### 9.4. Do not use unverified claim data

An unverified JWT is just a string supplied by the Client, even if it has clean JSON or a valid `kid`. Spring Security must verify it with trusted keys and the right issuer/audience **before** the converter runs. Never allow a fallback like "if JWKS is down, read roles from the payload", as that is **fail open**.

### 9.5. Bound roles/permissions accepted from tokens

The contract should constrain:

- Claim names and data shapes.
- Maximum count and length of roles/permissions that may appear.
- Allowed resources and actions.
- Which issuers/Clients are allowed to grant which permissions.
- Intended usage and access token lifetime.

Beyond an allowlist, high-abuse-risk systems can validate schema/size limits in the validation layer. Never let a token containing tens of thousands of entries generate tens of thousands of `GrantedAuthority` objects and cause memory or latency pressure.

### 9.6. Do not assume roles implicitly include permissions

If a system has a rule:

~~~text
ROLE_ORDER_SUPPORT -> PERM_order:read:tenant
~~~

you must decide **who is responsible for enforcing that rule**:

1. The Authorization Server emits permissions already derived from roles.
2. The Resource Server / role hierarchy applies a controlled rule.
3. A server-side policy engine looks up current entitlements.

Do not let all three places expand roles using different rules, which makes revocation unpredictable. **A role appearing in a JWT** does not necessarily mean the associated permission is still active at request time if privileges were updated after token issuance.

## 10. Example authorization by permission and ownership

A business contract might specify:

| Operation | OAuth2 Scope | Related permission/role | Data condition |
| --- | --- | --- | --- |
| Customer reads own order | `orders.read` | `PERM_order:read:own` | `order.ownerSubject` matches subject, matching tenant |
| Support reads tenant orders | `orders.read` | `PERM_order:read:tenant` | Caller is in support group and assigned tenant |
| Cancel own order | `orders.cancel` | `PERM_order:cancel:own` | Owner matches and order status allows cancellation |
| View audit reports | Dedicated scope per contract | Dedicated audit role/permission | Only datasets/tenants within granted scope |

A policy can be expressed logically as:

~~~text
canReadOrder =
    validAccessToken
    AND aud contains "orders-api"
    AND has("SCOPE_orders.read")
    AND (
      has("PERM_order:read:own") AND order.owner == caller.subject
      OR
      has("PERM_order:read:tenant")
          AND order.tenant IN caller.authorizedTenants
          AND caller.assignedGroup allows order
    )
~~~

In the expression above, `caller.authorizedTenants` and `assignedGroup` must come from **trusted data** or claims with agreed and verified semantics; never accept values self-declared by the Client in headers/queries without verification.

### 10.1. The role of `@PreAuthorize`

`@PreAuthorize` in section 7 blocks callers lacking the scope/permission before reading data; the `orderAccess` bean enforces conditions on the **actual order**. If an application only has:

~~~java
@PreAuthorize("hasRole('ORDER_SUPPORT')")
~~~

it does not yet know whether the support agent is allowed to view **orderId = 42** in another tenant. When permissions take a form like `read:tenant`, the real tenant must be verified in the business layer.

### 10.2. Avoid overly broad authorities

Do not map a permission object:

~~~json
{"resource": "orders", "scopes": ["read:tenant"]}
~~~

into `ROLE_ADMIN` just because a "generic" converter treats any permission as admin access. Authorities must reflect **exact capabilities**. Constraints on owner, tenant, region, customer contract, and object state still require independent policies.

## 11. Testing the converter and JWT verification are two separate layers

### 11.1. Unit testing the converter

With Spring Security, you can construct a `Jwt` in a unit test without creating a real signature. Example using JUnit Jupiter (placed in the same package as the config to access the package-private converter):

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

class NestedAuthoritiesConverterTest {

    private final JwtAuthorityMappingConfig.NestedAuthoritiesConverter
            converter =
            new JwtAuthorityMappingConfig.NestedAuthoritiesConverter(
                    "orders-api");

    @Test
    void mapsOnlyAllowedAuthoritiesFromOrdersApiContract() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only")
                .header("alg", "RS256")
                .claim("sub", "user-842")
                .claim("scope", "orders.read")
                .claim("realm_access", Map.of(
                        "roles", List.of(
                                "platform_auditor",
                                "default-roles-shop")))
                .claim("resource_access", Map.of(
                        "orders-api", Map.of(
                                "roles", List.of("order_support")),
                        "billing-api", Map.of(
                                "roles", List.of("billing_admin"))))
                .claim("authorization", Map.of(
                        "permissions", List.of(
                                Map.of(
                                        "resource", "orders",
                                        "scopes", List.of("read:tenant")),
                                Map.of(
                                        "resource", "reports",
                                        "scopes", List.of("export")))))
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);
        Set<String> names = result.stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());

        assertTrue(names.contains("SCOPE_orders.read"));
        assertTrue(names.contains("ROLE_PLATFORM_AUDITOR"));
        assertTrue(names.contains("ROLE_ORDER_SUPPORT"));
        assertTrue(names.contains("PERM_order:read:tenant"));

        assertFalse(names.contains("ROLE_BILLING_ADMIN"));
        assertFalse(names.contains("ROLE_DEFAULT_ROLES_SHOP"));
        assertFalse(names.contains("PERM_report:export:tenant"));
    }
}
~~~

This test proves **the rules converting claim data into authorities**, not that the JWT was properly signed. `Jwt.withTokenValue(...)` in a unit test does not go through `JwtDecoder` and performs no cryptographic verification.

### 11.2. Testing tokens with missing/malformed claims

The unit test suite should also cover:

| Input scenario | Converter result per example contract |
| --- | --- |
| Only `scope = orders.read` | Only `SCOPE_orders.read` |
| Missing `realm_access` | No realm-role authority |
| `resource_access` has `billing-api` roles but no `orders-api` | No Orders API role created |
| `orders-api.roles` is a string instead of an array | Does not convert string into role |
| Missing `authorization.permissions` | No permission authority created |
| Permission entry has `resource = reports` | Does not grant Orders permission |
| Permission has unallowed scope `delete:all` | Does not create a new authority |
| Repeated roles/permissions | Result has no duplicate authorities (set semantics) |
| Mandatory claim missing or violating schema | Dedicated validator rejects token per contract |

Remember to distinguish **tokens lacking permissions** from **tokens violating the contract**: if an optional role is absent, the caller gets no role; if a token profile requires a role/tenant yet violates the schema, a validator should fail the request at the authentication layer rather than silently omitting authorities.

### 11.3. Integration testing with real signatures

To test **SecurityFilterChain + JwtDecoder + converter**, tests must send **genuinely signed Bearer JWTs** using a test key, with mock JWKS and matching issuer/audience:

1. Validly signed token, matching issuer/audience, with `resource_access.orders-api.roles` → receives mapped authorities.
2. Token with identical payload but tampered signature → rejected **before** the converter.
3. Validly signed token with wrong audience → rejected despite carrying `tenant_admin`.
4. Valid token with roles under `billing-api` → receives no Orders API permissions.
5. Valid token with sufficient scope/permission, yet order belongs to another tenant → rejected by data policy.

`SecurityMockMvcRequestPostProcessors.jwt()` is convenient for testing authorization with a mocked `Authentication`, but **does not test real JWT signature/JWKS verification**. When testing structural access-token security, use integration tests going through the decoder.

## 12. Error responses: invalid token or insufficient permissions?

| Scenario | Rejection stage | Typical HTTP status |
| --- | --- | --- |
| Missing JWT, bad signature, wrong issuer/audience, expired | Authentication/`JwtDecoder` | **401 Unauthorized** |
| Verified JWT missing `orders.read` | HTTP authorization | **403 Forbidden** |
| JWT has read scope but lacks required permission | Method authorization | **403 Forbidden** |
| JWT has permission, but Order 42 belongs to another tenant | Resource policy | **403** or **404**, per policy |
| Missing optional nested role/permission | Converter produces no corresponding authority | Leads to **403** if endpoint requires it |
| Mandatory nested claim violates schema | Token validator | **401** per Bearer token handling |

Never return 403 for an unverified signature and implicitly treat it as having an identity. Conversely, a valid token lacking a scope/permission should not be reported as an "invalid signature". Recording errors at the right layer helps distinguish issuer issues, authority mapping bugs, and business policy denials.

## 13. Common implementation mistakes

### 13.1. Configuring only `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName` with a "path"

An easy mistake:

~~~java
converter.setAuthoritiesClaimName("realm_access.roles");
~~~

This is not a general JSONPath guaranteed to extract any nested claim. For a `realm_access` object, you must traverse the object and read `roles` with a custom converter.

### 13.2. Reusing every role in the token without checking its source

A token with `resource_access.billing-api.roles = ["admin"]` does not mean the caller is an admin of Orders API. Pulling all roles from all resources can create **cross-resource privilege escalation**.

### 13.3. Assuming nested roles are understood automatically by Spring Security

Spring JWT Resource Server does not automatically turn `roles`, `realm_access`, `resource_access`, or `authorization.permissions` claims into authorities. If `hasRole("ORDER_SUPPORT")` always returns 403, check that the converter is wired into `SecurityFilterChain` and that token mapping matches the schema.

### 13.4. Forgetting to preserve default scopes when replacing the converter

If a custom converter returns only roles, `SCOPE_orders.read` may disappear. Endpoints requiring scopes will return 403 even though the JWT has a `scope` claim. To keep default behavior, invoke `JwtGrantedAuthoritiesConverter` and merge the results.

### 13.5. Mixing up permission lists intended for another Resource Server

A permission object for `reports` is not automatically an `orders` permission. The contract must bind permissions to **specific resources/actions**, avoiding confusion where the same word `read` means different things.

### 13.6. Inconsistent role prefixes

If the converter creates `ROLE_ORDER_SUPPORT` while config checks `hasAuthority("ORDER_SUPPORT")`, it will not match. If using `hasRole("ORDER_SUPPORT")`, remember it typically checks `ROLE_ORDER_SUPPORT`.

### 13.7. Trusting claims before verification

Base64URL-decoding a JWT and using `roles` to populate `SecurityContext` is wrong. Claims must come from a token verified against trusted issuer/JWKS/algorithms/audience/expiration.

### 13.8. Treating roles in a JWT as real-time permission state

An issued JWT can hold stale roles/permissions until expiration if verified only offline. For frequently changing permissions or sensitive operations, you may need short-lived access tokens, server-side entitlement checks, revocation/introspection, or a dedicated policy service.

### 13.9. Treating `tenant_id` as automatic proof of access

A token with `tenant_id = tenant-A` is not enough to read every record in tenant-A. Verify that the principal still belongs to the tenant, that permissions apply to the right group/data, and check order state. Never rely on a tenant ID in the request body to expand privileges.

### 13.10. Trying to write one converter that "reads every issuer"

Identical JSON paths and role names do not guarantee identical semantics between two issuers. In a multi-issuer Resource Server, separate mappings per trusted issuer/profile and avoid merging permissions without a contract.

## 14. Weighing token-embedded permissions vs. dynamic lookups

There are two common strategies:

| Strategy | Benefits | Limitations |
| --- | --- | --- |
| **Roles/permissions embedded in JWT by AS** | API checks locally after verification; fewer network calls | Permissions can become stale, larger tokens, requires strict schema contract |
| **Resource Server looks up permissions from database/policy service** | Enforces up-to-date permissions and business rules | Depends on latency, caching, availability, and consistency |
| **Hybrid** | Token carries identity/scopes; backend computes policy from live data | Requires clear split of responsibilities to avoid conflicting permission sources |

A practical design is often **JWTs carrying scopes and identity info**, the converter mapping a few stable, meaningful roles/permissions, and the API checking owner/tenant/assignment from the database. If immediate revocation is needed when an account is locked, token claims alone are insufficient without a state-checking strategy.

## 15. Sample contract document for Identity and API teams

Before implementing a converter, both teams can maintain a concise document:

~~~yaml
# Illustrative contract, not a file automatically read by Spring.
resource_server: orders-api
trusted_issuer: https://id.example.test/realms/shop
expected_audience: orders-api
token_type: oauth2_access_token

claims:
  oauth_scopes:
    path: scope
    type: "space-delimited string"
    authority_prefix: "SCOPE_"
  realm_roles:
    path: realm_access.roles
    type: "array<string>"
    allowed:
      platform_auditor: ROLE_PLATFORM_AUDITOR
  api_roles:
    path: resource_access["orders-api"].roles
    type: "array<string>"
    allowed:
      order_support: ROLE_ORDER_SUPPORT
      tenant_admin: ROLE_TENANT_ADMIN
  permissions:
    path: authorization.permissions
    type: "array<object>"
    filter_resource: orders
    resource_scopes:
      "read:own": "PERM_order:read:own"
      "read:tenant": "PERM_order:read:tenant"
      "cancel:own": "PERM_order:cancel:own"

authorization:
  read_orders:
    required_scope: orders.read
    required_any_permission:
      - PERM_order:read:own
      - PERM_order:read:tenant
    data_policy: "owner/tenant/assignment must match"
  cancel_orders:
    required_scope: orders.cancel
    required_permission: PERM_order:cancel:own
    data_policy: "owner matches and order state allows cancellation"

missing_optional_claims: no_authority_granted
unrecognized_role_or_permission: ignored
missing_required_claims: invalid_token
~~~

This document needs extensions if production involves multiple issuers, multiple tenants, Client Credentials, differently shaped nested claims, custom token profiles, role hierarchies, or dynamic permissions. When schemas change, **update the contract first, then update the converter and policies together** so older APIs do not accidentally interpret new claims too broadly.

## 16. Scenario questions for self-practice

**Scenario A — Token has Billing Admin role:** A valid JWT has `resource_access.billing-api.roles = ["billing_admin"]` but no role under `orders-api`. Does Orders API grant `ROLE_TENANT_ADMIN`?

**No.** The converter only reads roles for the resource/client contracted with Orders API. Roles from Billing API are not inherited automatically.

**Scenario B — Token has Support role but lacks scope:** A JWT has `resource_access.orders-api.roles = ["order_support"]`, while `scope` is only `profile`. The endpoint requires `SCOPE_orders.read`. Outcome?

Per the example contract, **403 Forbidden**. A role does not substitute for a scope when policy requires both.

**Scenario C — Token has an unlisted permission:** `authorization.permissions` lists `resource = orders`, `scopes = ["delete:all"]`. Does the converter create `PERM_order:delete:all`?

**No.** The mapping table contains only agreed actions; unfamiliar permissions do not create new authorities.

**Scenario D — Unverified JWT with nested admin role:** A developer decodes the payload and creates `ROLE_TENANT_ADMIN` before checking the signature. What is wrong?

The developer **used untrusted data for authentication/authorization**. Role extraction must occur after `JwtDecoder` completes token verification.

**Scenario E — Scope and permission match, order belongs to another tenant:** A JWT carries `SCOPE_orders.read` and `PERM_order:read:tenant`, yet the order belongs to a tenant outside the granted range. Is reading allowed?

**No.** Permissions state the type of capability; owner/tenant/assignment on the record must still satisfy the policy.

**Scenario F — Unit test using `Jwt.withTokenValue(...)` passed:** Can we claim JWS/JWKS and issuer/audience verification are working?

**Not yet.** Converter unit tests only verify mapping. Integration tests sending genuinely signed JWTs through the decoder are required to verify the authentication boundary.

**Scenario G — AS adds a new role `order_manager`:** If the converter uses an allowlist table with no mapping for it yet, does the new role automatically become an authority?

**No.** This is the desired behavior: opening up new privileges requires updating the contract and a deliberate decision by the API team.

---

## Conclusion

**Nested roles and permissions in a JWT are issuer-contracted data, not an automatic Spring Security authorization mechanism.** The default `JwtGrantedAuthoritiesConverter` mainly handles OAuth2 scopes; to use paths like `realm_access.roles`, `resource_access["orders-api"].roles`, and `authorization.permissions[].scopes`, an application needs a custom converter that reads the exact structure, scopes extraction to the right source/resource, maps through an **allowlist table**, and merges authorities with clear prefixes.

In all cases, **verify signature, issuer, audience, expiration, and token profile before using claims**. A converter does not replace validators and should never expand privileges beyond what was agreed upon. Even after obtaining `SCOPE_`, `ROLE_`, and `PERM_`, the Resource Server must still check **permissions on the specific resource** by owner, tenant, status, and system policy.
