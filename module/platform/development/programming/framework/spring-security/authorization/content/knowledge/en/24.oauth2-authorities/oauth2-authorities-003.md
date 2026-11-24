# Role Claim Mapping and Controlling the `ROLE_` Prefix

> **Module:** Spring Security – authorization · **Group:** Authorities from OAuth2. This lesson explains end-to-end how to convert permissions inside an OAuth 2.0/OIDC access token into `GrantedAuthority` instances that Spring Security can evaluate, accurately distinguishing **roles** from **scopes**, applying the `ROLE_` prefix strictly once, and avoiding turning another application's or tenant's claim into admin privilege. The main examples use **Spring Boot 3.5.x, Spring Security 6.5.x, Java 17+**, Servlet OAuth2 Resource Server JWT. Separate sections cover `oauth2Login()` and WebFlux because their authority conversion pipelines differ. Tokens in this lesson are simulated data, not real credentials.

## 1. What should you understand and be able to do after this lesson?

1. Understand that after `JwtDecoder` verifies signature/issuer/audience/expiry, `JwtAuthenticationConverter` converts the JWT access token into an `Authentication`.
2. Explain why `scope: "reports.read"` typically becomes authority `SCOPE_reports.read` and does not automatically become role `ROLE_ADMIN`.
3. Distinguish `hasRole("ADMIN")`, `hasAuthority("ROLE_ADMIN")`, `hasAuthority("ADMIN")`, and `hasAuthority("SCOPE_reports.read")`; know where prefixes are needed.
4. Configure `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName` and `setAuthorityPrefix` for a flat role claim; understand that **merely replacing the converter can lose the default scope authorities**.
5. Build a converter that combines allow-listed scopes + roles while separating realm/global roles from client/resource-specific permissions.
6. Avoid `ROLE_ROLE_ADMIN` when the IdP already sends a prefixed role; never silently treat an invalid string as ADMIN.
7. Parse nested claims such as `realm_access.roles` and `resource_access["orders-api"].roles` via explicit traversal, without assuming `setAuthoritiesClaimName("realm_access.roles")` traverses JSON paths automatically.
8. Configure Spring `SecurityFilterChain` and `@PreAuthorize` consistently with the emitted authorities, using issuer/audience validation to establish which API a token is meant for.
9. Test the converter, test the HTTP resource-server filter with a mocked `JwtDecoder`, and plan real signature/JWKS verification in integration tests.
10. Distinguish resource server role mapping from `oauth2Login().userInfoEndpoint().userAuthoritiesMapper(...)` and `ReactiveJwtAuthenticationConverter`.
11. Account for role changes, global roles vs. tenant-scoped permissions, audience/client isolation, least privilege, and caching/revocation.
12. Run a standalone Java 17 program simulating prefix mapping with predictable stdout results.

## 2. What happens when the API receives a Bearer JWT?

Typical processing flow on a Servlet resource server:

~~~text
HTTP Authorization: Bearer <opaque-token-bytes>
  |
  v
BearerTokenAuthenticationFilter
  |
  v
JwtAuthenticationProvider
  |
  +-- JwtDecoder: verify JWS signature, issuer, exp, nbf,
  |                audience and any required custom validation
  |
  v
JwtAuthenticationConverter
  |
  +-- Converter<Jwt, Collection<GrantedAuthority>>
  |       |-- scopes -> SCOPE_reports.read, SCOPE_orders.read
  |       |-- curated roles -> ROLE_ADMIN, ROLE_AUDITOR
  |       |-- app-specific permissions -> PERM_ORDERS_WRITE
  |
  v
JwtAuthenticationToken(Authentication)
  |
  v
SecurityFilterChain / method security AuthorizationManager
  |
  +-- hasRole("ADMIN")                 tests ROLE_ADMIN
  +-- hasAuthority("ROLE_ADMIN")       tests exact ROLE_ADMIN
  +-- hasAuthority("SCOPE_reports.read") tests exact SCOPE_reports.read
  +-- hasAuthority("PERM_ORDERS_WRITE")  tests exact PERM_ORDERS_WRITE
~~~

**Three concepts that must not be conflated:**

- **OAuth 2.0 scope** is the permission/scope granted by an authorization server to an access token/client. It typically uses names such as `orders.read`, `orders.write`, `profile`. By default, Spring maps it to authorities starting with `SCOPE_`.
- **Role** is a business or administrative responsibility group, such as `ADMIN`, `AUDITOR`, `VIEWER`; Spring typically expects authorities starting with `ROLE_` for convenient `hasRole` checks.
- **Permission/authority** is the exact string checked by authorization logic, such as `PERM_ORDERS_WRITE` or `document:approve`. There is no mandatory rule that it must start with `ROLE_`.

Roles are not automatically generated from a JWT if the IdP does not send them or the application does not map them. Conversely, having `roles=["ADMIN"]` in a JWT does **not** make Spring automatically add `ROLE_ADMIN` in the default JWT Resource Server configuration.

### 2.1. Example access token from an IdP

Illustrative JWT payload:

~~~json
{
  "iss": "https://idp.example.invalid/realms/acme",
  "sub": "user-7",
  "aud": ["orders-api"],
  "iat": 1783310000,
  "exp": 1783313600,
  "scope": "reports.read orders.read",
  "roles": ["ADMIN", "VIEWER"],
  "realm_access": {
    "roles": ["AUDITOR"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["write"]
    },
    "other-client": {
      "roles": ["admin"]
    }
  }
}
~~~

Do not use these timestamps to infer token validity; they only illustrate claim structure. Never copy a mock token into an API credential. **A JWT payload by itself is untrusted** until `JwtDecoder` verifies the JWS signature, trusted algorithm, issuer, audience, and lifetime.

A token can contain multiple role sources. Do not take the approach of "walk the whole JSON and create `ROLE_ADMIN` whenever the string `admin` appears." In the example, the `admin` role under `other-client` must **not** grant admin access to `orders-api`.

## 3. Meaning of the `ROLE_` prefix down to the character

Spring Security treats `GrantedAuthority#getAuthority()` as a string to match. `SimpleGrantedAuthority("ROLE_ADMIN")` is simply an authority with that exact name.

| User/token mapped authority | Rule | Result in default configuration |
| --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | GRANT |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | GRANT |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | DENY |
| `ADMIN` | `hasRole("ADMIN")` | DENY |
| `SCOPE_orders.read` | `hasRole("orders.read")` | DENY |
| `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` | GRANT |
| `ROLE_VIEWER` | `hasRole("ADMIN")` | DENY |
| `ROLE_ROLE_ADMIN` | `hasRole("ADMIN")` | DENY |
| `PERM_ORDERS_WRITE` | `hasAuthority("PERM_ORDERS_WRITE")` | GRANT |

**Default semantics:**
- `hasRole("ADMIN")` is a shortcut checking for a `GrantedAuthority` named `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` checks for the exact authority `ROLE_ADMIN`, adding no prefix.
- `hasAuthority("ADMIN")` checks for the exact string `ADMIN`.
- `@PreAuthorize("hasRole('ADMIN')")` also targets `ROLE_ADMIN` under the default role prefix.
- In some DSLs, `hasRole("ROLE_ADMIN")` is even rejected because the argument already carries the prefix; the most consistent convention is **omit the prefix in `hasRole`, include the prefix in `hasAuthority`**.
- String matching is case-sensitive: `admin` ≠ `ADMIN`, `ROLE_admin` ≠ `ROLE_ADMIN`.

### 3.1. Two different "prefix settings"

**(A) Converter mapping from claim:**

~~~java
JwtGrantedAuthoritiesConverter converter =
        new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("roles");
converter.setAuthorityPrefix("ROLE_");
~~~

For example, claim `roles:["ADMIN"]` produces `ROLE_ADMIN`. This is how the converter **creates** the authority string.

**(B) Authorization rule:**

~~~java
.requestMatchers("/api/admin").hasRole("ADMIN")
// or @PreAuthorize("hasAuthority('ROLE_ADMIN')")
~~~

This is how the application **checks** the authority string. Changing `setAuthorityPrefix("ROLE_")` does not automatically update every Spring DSL so that all roles match; you must verify both ends with tests.

### 3.2. Where does "ROLE_ROLE_ADMIN" come from?

If the IdP sends:

~~~json
{"roles":["ROLE_ADMIN"]}
~~~

and the converter still uses `setAuthorityPrefix("ROLE_")`, the result can be `ROLE_ROLE_ADMIN`. A `hasRole("ADMIN")` rule will not match. Do not fix this by casually calling `hasRole("ROLE_ADMIN")` or issuing `ROLE_ROLE_ADMIN` as well.

Pick **one** contract:
- IdP sends bare role names `ADMIN`, and the converter adds `ROLE_` once.
- IdP sends `ROLE_ADMIN`, and the converter uses an empty prefix (`""`) **only if that source is strictly governed**.
- With mixed sources, a custom converter uses an **explicit allow-list and canonical mapping**, rejecting pre-prefixed strings or normalizing per reviewed rules rather than arbitrarily stripping duplicate `ROLE_` prefixes.

### 3.3. Do not reconfigure `ROLE_` globally just to patch one claim

`GrantedAuthorityDefaults("CUSTOM_")` can change the default role prefix in contexts such as method security expressions. However, do not assume every API DSL, converter, and custom `AuthorizationManager` automatically honors that setting. In particular, the traditional `AuthorityAuthorizationManager.hasRole(...)` factory builds `ROLE_` requirements per its own contract. Unless there is a clear architectural reason, keeping the default `ROLE_` is easier to audit, and using explicit `hasAuthority(...)` works when a different prefix is needed.

If you change the default prefix, write tests for **request authorization, method authorization, role hierarchy, and any custom managers**, rather than extrapolating from a single test.

## 4. How does Spring map JWT scopes by default?

With a standard Resource Server JWT configuration, Spring Security looks for well-known claims such as `scope` or `scp` and creates authorities prefixed with `SCOPE_`.

~~~json
{"scope":"orders.read reports.read"}
~~~

typically becomes:

~~~text
SCOPE_orders.read
SCOPE_reports.read
~~~

A provider may also use:

~~~json
{"scp":["orders.read","reports.read"]}
~~~

The default converter handles supported well-known formats. Additional claims such as `roles` or Keycloak's `realm_access.roles` are **not automatically** converted to `ROLE_*`.

In `JwtGrantedAuthoritiesConverter`:
- `setAuthoritiesClaimName("roles")` tells the converter to read the top-level `roles` field instead of the well-known scope fields.
- `setAuthorityPrefix("ROLE_")` prepends the prefix to each authority it generates.
- `setAuthorityPrefix("")` removes the prefix for the field being read, without changing how `hasRole` checks by default.
- `setAuthoritiesClaimDelimiter(regex)` (Spring Security 6.1+) splits a string-formatted claim by regex; it does not resolve nested JSON paths.
- If the `roles` claim is a properly typed list, the converter creates one authority per value. If roles are nested or have a custom shape, a custom converter is required.

**Critical risk:** if you completely replace the default converter with one that reads only `roles`, previously generated `SCOPE_*` authorities can **disappear**. An endpoint relying on `SCOPE_reports.read` may start returning 403. Conversely, trying to "fix" this by changing the prefix on **scopes** to `ROLE_` can accidentally turn `scope="ADMIN"` into `ROLE_ADMIN`—an over-privilege risk when scopes and business roles have different issuers or governance.

## 5. Before mapping roles, verify the access token is trustworthy

Role claims must only be used after the JWT is properly validated. `JwtDecoder` must verify:
- JWS signature using keys from a trusted issuer; never allow the `"none"` algorithm or trust a base64-decoded payload.
- Exact `iss` issuer; never accept tokens from arbitrary client-supplied IdPs/realms.
- `exp`, `nbf`, and appropriate clock skew.
- `aud` contains the audience of **this resource server**. A token issued for a GraphQL frontend or another API is not implicitly valid for `orders-api`.
- Issuer/client/azp/tenant/token_type/claims constraints as required by the system; do not treat `aud` as the entirety of the trust model.
- Only token types with a trusted role claim contract; never use an OIDC ID token issued for client login as a resource API access token.
- Key rotation/JWKS caching and allowed algorithms matching the provider.

Illustrative Spring Boot 3.5 Resource Server configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realms/acme
          audiences: orders-api
~~~

This is a **placeholder URL** that must be replaced with real issuer metadata upon deployment. The `issuer-uri` property configures issuer validation and key discovery; `audiences` adds audience validation for the corresponding Boot version. If defining a custom `JwtDecoder`, preserve all required validators; creating a custom decoder while forgetting issuer/audience validation is a critical bug.

**Distinguishing 401 and 403:**
- Missing/invalid JWT signature, expired token, or invalid issuer/audience → authentication failure, typically HTTP **401**.
- Valid, authenticated JWT lacking the required authority → authorization failure, typically HTTP **403**.

Do not turn a 403 into 200 just because the token is "valid." Conversely, a role claim named `ADMIN` is not proof that the token has the right audience.

## 6. Simple case: roles as a top-level claim

If the provider guarantees the access token sends:

~~~json
{"roles":["ADMIN","EDITOR"]}
~~~

and the system relies **only** on roles, you can configure:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter roles = new JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");

JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(roles);

// After JwtDecoder has validated the token:
// roles ["ADMIN", "EDITOR"] -> ROLE_ADMIN, ROLE_EDITOR.
~~~

This is a **Java snippet inside a method/config bean**, not a standalone Java file; imports are wrapped for readability and should be placed on single lines if copied directly. Real configuration must wire the converter into `oauth2ResourceServer(...).jwt(...)`.

**Limitations:**
1. This configuration replaces the default scope mapping; if the API also uses `SCOPE_orders.read`, you must **combine**, not replace.
2. `setAuthoritiesClaimName("roles")` does not traverse into `realm_access.roles` or `resource_access["orders-api"].roles`.
3. A token already sending `ROLE_ADMIN` can become double-prefixed.
4. The converter does not know which roles are actually permitted, who a trusted issuer is, or whether the token has the right audience; those belong to authentication validation and claim contracts.
5. In multi-tenant or multi-client systems, a top-level `ADMIN` role is ambiguous without scope qualification; do not treat it as a SaaS-wide superuser.

The next section uses an allow-listed, namespace-aware converter that preserves scopes while mapping roles.

## 7. Safer converter: keep `SCOPE_`, add `ROLE_` strictly once

### 7.1. Policy of the example

Suppose the `orders-api` accepts three sources from a **verified issuer**:
- `scope`/`scp` → keep `SCOPE_<scope>` via the default converter.
- Top-level `roles` and `realm_access.roles` → only names matching the allow-list `ADMIN`, `EDITOR`, `VIEWER`, `AUDITOR` become `ROLE_<name>`.
- `resource_access["orders-api"].roles` → `read`/`write` roles map to `PERM_ORDERS_READ`/`PERM_ORDERS_WRITE`. Never turn `other-client`'s `admin` role into a global `ROLE_ADMIN`.

This is an **illustrative contract**; in real deployments, evaluate whether the provider/realm guarantees that `ADMIN` truly represents a global admin of `orders-api`. If not, restrict/forbid mapping `ADMIN` from realm/global claims; inspect only claims scoped specifically to the resource API and enforce fine-grained permissions.

### 7.2. Complete `ScopesAndRolesConverter.java`

Save `src/main/java/demo/authz/ScopesAndRolesConverter.java`:

~~~java
package demo.authz;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

/**
 * Spring Security 6.5.x, Java 17+.
 * Invoke this converter ONLY AFTER JwtDecoder validates the token.
 * Performs no I/O and does not read HttpServletRequest.
 */
final class ScopesAndRolesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final Set<String> GLOBAL_ROLES =
            Set.of("ADMIN", "EDITOR", "VIEWER", "AUDITOR");

    private static final Map<String, String> ORDER_PERMISSIONS =
            Map.of(
                "read", "PERM_ORDERS_READ",
                "write", "PERM_ORDERS_WRITE");

    // Delegate preserves scope/scp -> SCOPE_xxx per Spring defaults.
    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        LinkedHashSet<GrantedAuthority> result =
                new LinkedHashSet<>(scopes.convert(jwt));

        // Top-level claim.
        addGlobalRoles(jwt.getClaims().get("roles"), result);

        // Realm roles: only fields agreed in contract with trusted issuer.
        Object realmRoles = child(
                jwt.getClaims().get("realm_access"), "roles");
        addGlobalRoles(realmRoles, result);

        // Only orders-api client: never iterate over all clients.
        Object ordersRoles = child(
                child(jwt.getClaims().get("resource_access"),
                        "orders-api"),
                "roles");
        addOrderPermissions(ordersRoles, result);

        return List.copyOf(result);
    }

    private static Object child(Object candidate, String key) {
        if (candidate instanceof Map<?, ?> map) {
            return map.get(key);
        }
        return null;
    }

    private static void addGlobalRoles(
            Object candidate, Set<GrantedAuthority> result) {
        if (!(candidate instanceof Collection<?> names)) {
            return; // Missing or wrong type: grant no role.
        }
        for (Object item : names) {
            if (item instanceof String role
                    && GLOBAL_ROLES.contains(role)) {
                result.add(new SimpleGrantedAuthority(
                        "ROLE_" + role));
            }
        }
    }

    private static void addOrderPermissions(
            Object candidate, Set<GrantedAuthority> result) {
        if (!(candidate instanceof Collection<?> names)) {
            return;
        }
        for (Object item : names) {
            if (item instanceof String role) {
                String permission = ORDER_PERMISSIONS.get(role);
                if (permission != null) {
                    result.add(
                        new SimpleGrantedAuthority(permission));
                }
            }
        }
    }
}
~~~

**Why does this design control `ROLE_` better?**
- `GLOBAL_ROLES.contains(role)` accepts only exact contracted names, rejecting `ROLE_ADMIN`, `admin`, `SUPERADMIN`, whitespace, or similar variants.
- There is no arbitrary "add `ROLE_` if missing, strip if present" loop; wrong shapes are ignored and grant no authority.
- `LinkedHashSet` deduplicates across `roles` and `realm_access.roles`, keeping the result deterministic.
- `scope/scp` continues to be handled by the delegate, so `SCOPE_reports.read` remains intact.
- Client role `write` grants only `PERM_ORDERS_WRITE`, avoiding escalation to global `ROLE_ADMIN`.
- Only the `orders-api` key inside `resource_access` is read; `other-client.roles` is completely ignored.
- No roles are taken from user-submitted `X-Role` headers or form bodies; only from a JWT validated by `JwtDecoder`.

**Area for improvement per organizational policy:** if roles are tenant-specific, the converter should not emit a global `ROLE_ADMIN`. You can emit `TENANT_<opaque-id>_ROLE_ADMIN` under a controlled schema, while tenant-specific resource checks must still consult a trusted tenant/member/ACL source rather than relying solely on an authority string built from client input.

### 7.3. Notes on claim types and nested fields

`JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName("realm_access.roles")` generally looks for a literal top-level claim key named `realm_access.roles`, not a JSON-path parser. For JSON:

~~~json
{"realm_access":{"roles":["AUDITOR"]}}
~~~

the claim is actually a `Map` inside the `realm_access` field. The custom converter above checks `instanceof Map<?, ?>` and reads `roles` at the right level.

If the IdP sends `roles` as a space-delimited string `"ADMIN EDITOR"` rather than an array, standardize the schema:
- Use `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimDelimiter("\\s+")` on a dedicated converter reading only that string claim.
- Or parse via an explicit, tested parser that rejects malformed/mixed types.
- Never parse JSON with `toString().contains("ADMIN")`, `split(",")` on nested objects, or ad-hoc regexes over raw tokens.
- If a provider changes claim shape, prefer failing contract checks/metrics and denying access rather than "guessing" admin.

## 8. Spring Boot 3.5 Resource Server: real configuration and endpoints

Create a Java 17+, Spring Boot 3.5.x project with `web`, `security`, and `oauth2-resource-server` starters. Use JWT access tokens for the Servlet API; **do not add OAuth2 Login just because you use OAuth2 Resource Server**.

Create two files:
- `src/main/java/demo/authz/ScopesAndRolesConverter.java` (Section 7).
- `src/main/java/demo/authz/RoleClaimApplication.java` (below).

### 8.1. `RoleClaimApplication.java`

~~~java
package demo.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class RoleClaimApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleClaimApplication.class, args);
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
                new ScopesAndRolesConverter());
        // Principal defaults to sub; never derive roles from subject.
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        // hasRole automatically checks ROLE_ADMIN.
                        .requestMatchers("/api/admin")
                            .hasRole("ADMIN")
                        // Method security checks permissions/scopes.
                        .requestMatchers("/api/orders/check",
                                         "/api/reports")
                            .authenticated()
                        .anyRequest().denyAll())
                .oauth2ResourceServer(resourceServer ->
                    resourceServer.jwt(jwt ->
                        jwt.jwtAuthenticationConverter(
                            jwtAuthenticationConverter)))
                .build();
    }
}

@Service
class SecureBusinessService {
    @PreAuthorize("hasAuthority('PERM_ORDERS_WRITE')")
    public String checkOrderWrite() {
        return "orders-write-allowed";
    }

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public String readReport() {
        return "reports-read-allowed";
    }
}

@RestController
class RoleEndpoints {
    private final SecureBusinessService service;

    RoleEndpoints(SecureBusinessService service) {
        this.service = service;
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin-allowed";
    }

    @GetMapping("/api/orders/check")
    String orders() {
        return service.checkOrderWrite();
    }

    @GetMapping("/api/reports")
    String reports() {
        return service.readReport();
    }
}
~~~

**Design rationale:**
1. The resource server JWT decoder validates the token before the converter runs.
2. `jwtAuthenticationConverter` uses the combined converter to preserve `SCOPE_*` and generate `ROLE_*`/`PERM_*` per claim contract.
3. `requestMatchers("/api/admin").hasRole("ADMIN")` checks `ROLE_ADMIN`. Never write `hasRole("ROLE_ADMIN")`.
4. `/api/orders/check` requires authentication at the filter layer, while `SecureBusinessService.checkOrderWrite()` enforces `PERM_ORDERS_WRITE` via `@EnableMethodSecurity` and `@PreAuthorize` on a Spring bean.
5. `/api/reports` requires `SCOPE_reports.read`; if scope mapping had been accidentally overwritten by a roles-only converter, this test would return 403 and catch the bug.
6. `anyRequest().denyAll()` prevents accidentally exposing new routes.
7. The demo uses GET endpoints purely to check authorities; in real products, WRITE/DELETE operations require appropriate HTTP methods, resource/tenant ownership, CSRF policy if sessions exist, transactions, and auditing.
8. Service invocations must pass through a Spring-managed proxy; calling `this.checkOrderWrite()` internally within the same bean can bypass method-security advice in Spring AOP proxy mode.

### 8.2. `build.gradle` dependencies

In a project with the Spring Boot Gradle plugin, repositories, and Java 17 already configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Boot resource server starter pulls in the required BOM-managed JWT/Jose dependencies; avoid mixing different versions of `spring-security` modules. This setup targets Boot 3.5/Security 6.5 so `@MockitoBean` is available in tests.

### 8.3. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realms/acme
          audiences: orders-api
~~~

This is a structurally valid placeholder issuer with no real IdP behind it. You cannot call a production API with a token whose claims you modified yourself. In real environments, use the official issuer URL and the audience issued by the IdP for this API; configure trusted algorithms/key rotation and token lifetimes per organizational policy.

**Do not** include `spring.security.oauth2.client.registration...` in this Resource Server demo. OAuth2 Login configurations for OIDC web sign-in belong to a different flow (see Section 12).

### 8.4. Expected matrix for the demo

| Decoded access token | Authorities after converter | `/api/admin` | `/api/orders/check` | `/api/reports` |
| --- | --- | --- | --- | --- |
| role ADMIN; client orders-api/write; scope reports.read | `ROLE_ADMIN`, `PERM_ORDERS_WRITE`, `SCOPE_reports.read` | 200 | 200 | 200 |
| role VIEWER; scope reports.read | `ROLE_VIEWER`, `SCOPE_reports.read` | 403 | 403 | 200 |
| role `ROLE_ADMIN`; no bare ADMIN role | No `ROLE_ADMIN` from this role | 403 | Per remaining permissions | Per remaining scopes |
| only other-client/admin | Does not grant orders-api admin | 403 | 403 | Per remaining scopes |
| Valid JWT with no roles/scopes | Empty | 403 | 403 | 403 |
| Invalid signature/issuer/audience/expired | Authentication rejected | 401 | 401 | 401 |

Results may change if you add authorization filters, role hierarchies, or custom exception handling; however, the rule **never mis-map roles/permissions** remains unchanged.

## 9. Converter unit tests: catching double prefixes, nested claims, and preserved scopes

Save `src/test/java/demo/authz/ScopesAndRolesConverterTest.java`:

~~~java
package demo.authz;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ScopesAndRolesConverterTest {
    private final ScopesAndRolesConverter converter =
            new ScopesAndRolesConverter();

    private Jwt jwt(Object roles, Object realmAccess,
                    Object resourceAccess) {
        return Jwt.withTokenValue("unit-test-only")
                .header("alg", "RS256")
                .claim("sub", "user-7")
                .claim("scope", "reports.read orders.read")
                .claim("roles", roles)
                .claim("realm_access", realmAccess)
                .claim("resource_access", resourceAccess)
                .build();
    }

    private Set<String> names(Jwt jwt) {
        return converter.convert(jwt).stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());
    }

    @Test
    void keepsScopesAndMapsOnlyApprovedRoles() {
        Jwt token = jwt(
                List.of("ADMIN", "ROLE_ADMIN", "unknown"),
                Map.of("roles", List.of("AUDITOR")),
                Map.of(
                    "orders-api", Map.of("roles", List.of("write")),
                    "other-client", Map.of("roles", List.of("admin"))));

        assertEquals(Set.of(
                "SCOPE_reports.read",
                "SCOPE_orders.read",
                "ROLE_ADMIN",
                "ROLE_AUDITOR",
                "PERM_ORDERS_WRITE"), names(token));
    }

    @Test
    void alreadyPrefixedAndUnknownRolesDoNotGrantAdmin() {
        Jwt token = jwt(
                List.of("ROLE_ADMIN", "admin", "SUPERADMIN"),
                Map.of("roles", List.of("ROLE_ADMIN")),
                Map.of("other-client",
                        Map.of("roles", List.of("admin"))));

        Set<String> authorities = names(token);
        assertFalse(authorities.contains("ROLE_ADMIN"));
        assertFalse(authorities.contains("ROLE_ROLE_ADMIN"));
        assertFalse(authorities.contains("PERM_ORDERS_WRITE"));
        assertTrue(authorities.contains("SCOPE_reports.read"));
    }

    @Test
    void malformedClaimsDoNotCreateRoles() {
        Jwt token = jwt(
                "ADMIN",
                Map.of("roles", "ADMIN"),
                Map.of("orders-api", Map.of("roles", 123)));

        Set<String> authorities = names(token);
        assertEquals(Set.of(
                "SCOPE_reports.read", "SCOPE_orders.read"),
                authorities);
    }

    @Test
    void duplicateRolesBecomeOneAuthority() {
        Jwt token = jwt(
                List.of("ADMIN", "ADMIN"),
                Map.of("roles", List.of("ADMIN")),
                Map.of());

        Set<String> authorities = names(token);
        assertEquals(1, authorities.stream()
                .filter("ROLE_ADMIN"::equals).count());
    }
}
~~~

**What the tests verify:**
- Tests real mapping on a `Jwt` Java object; the `alg=RS256` header in tests **is unsigned**, serving purely as a fixture to test the converter.
- Authorities are compared as sets to avoid order sensitivity.
- A pre-prefixed `ROLE_ADMIN` claim is ignored, creating neither `ROLE_ROLE_ADMIN` nor `ROLE_ADMIN`.
- `other-client.roles` grants neither permissions nor global roles.
- When nested fields have wrong types, the converter grants no extra roles.
- Scopes remain preserved by default, letting tests catch accidental converter replacement that drops scope mapping.
- These unit tests do not prove token signature, issuer, audience, or expiry validation: that is the job of the decoder and integration tests.

## 10. MockMvc with mocked `JwtDecoder`: testing `SecurityFilterChain` and method security

Many examples use:

~~~java
mvc.perform(get("/api/admin")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("ROLE_ADMIN"))));
~~~

Tests with `jwt().authorities(...)` **manually set authorities**, so they can PASS even when the production converter is misconfigured! To test the authorities pipeline properly, the approach below sends a Bearer token into the resource-server filter and mocks **only `JwtDecoder`** to return a defined `Jwt`. The real converter and authorization layers still run.

This lesson uses Spring Boot **3.5.x**, which includes Spring Framework `@MockitoBean`. Save `src/test/java/demo/authz/RoleClaimApplicationTest.java`:

~~~java
package demo.authz;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class RoleClaimApplicationTest {
    @Autowired MockMvc mvc;

    @MockitoBean JwtDecoder decoder;

    private Jwt token(String tokenValue, Object roles,
                      String scope, Object resourceAccess) {
        return Jwt.withTokenValue(tokenValue)
                .header("alg", "RS256")
                .claim("sub", "user-7")
                .claim("scope", scope)
                .claim("roles", roles)
                .claim("resource_access", resourceAccess)
                .build();
    }

    @BeforeEach
    void decoderFixtures() {
        when(decoder.decode("admin-token"))
                .thenReturn(token(
                    "admin-token", List.of("ADMIN"),
                    "reports.read",
                    Map.of("orders-api",
                        Map.of("roles", List.of("write")))));

        when(decoder.decode("viewer-token"))
                .thenReturn(token(
                    "viewer-token", List.of("VIEWER"),
                    "reports.read", Map.of()));

        when(decoder.decode("double-prefix-token"))
                .thenReturn(token(
                    "double-prefix-token", List.of("ROLE_ADMIN"),
                    "", Map.of()));

        when(decoder.decode("other-client-token"))
                .thenReturn(token(
                    "other-client-token", List.of(),
                    "", Map.of("other-client",
                        Map.of("roles", List.of("admin")))));

        when(decoder.decode("invalid-token"))
                .thenThrow(new BadJwtException("invalid token"));
    }

    private org.springframework.test.web.servlet.request
        .MockHttpServletRequestBuilder bearer(
            String path, String token) {
        return get(path).header(
                "Authorization", "Bearer " + token);
    }

    @Test
    void approvedRoleMatchesHasRole() throws Exception {
        mvc.perform(bearer("/api/admin", "admin-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-allowed"));
    }

    @Test
    void appSpecificPermissionMatchesMethodSecurity()
            throws Exception {
        mvc.perform(bearer("/api/orders/check", "admin-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("orders-write-allowed"));
    }

    @Test
    void scopesSurviveRoleMapping() throws Exception {
        mvc.perform(bearer("/api/reports", "viewer-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("reports-read-allowed"));
    }

    @Test
    void viewerCannotCallAdminOrWriteOrder()
            throws Exception {
        mvc.perform(bearer("/api/admin", "viewer-token"))
                .andExpect(status().isForbidden());
        mvc.perform(bearer("/api/orders/check", "viewer-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void roleAlreadyPrefixedIsNotAdmin() throws Exception {
        mvc.perform(bearer("/api/admin", "double-prefix-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unrelatedClientRoleDoesNotGrant() throws Exception {
        mvc.perform(bearer("/api/admin", "other-client-token"))
                .andExpect(status().isForbidden());
        mvc.perform(bearer("/api/orders/check",
                           "other-client-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenIsUnauthenticated() throws Exception {
        mvc.perform(bearer("/api/admin", "invalid-token"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingBearerTokenIsUnauthenticated()
            throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**Note when copying:** Java imports cannot wrap across lines inside a package/class name. In the snippet above, the `bearer(...)` helper signature is line-wrapped for Markdown, so the return type must be written on **one continuous line** as `org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder`, or else import `MockHttpServletRequestBuilder` and use the single-word type name. The simplest way when applying it is:

~~~java
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

// Replace only the helper method declaration in the test:
private MockHttpServletRequestBuilder bearer(
        String path, String token) {
    return get(path).header(
            "Authorization", "Bearer " + token);
}
~~~

The other imports in the test file above are complete for Boot 3.5; only the helper has a cleaner formatting option for the Java parser. **Do not copy both `bearer` declarations at once.** This lesson intentionally explains where formatting normalization is needed, not an example that compiles two helpers.

### 10.1. Which tests are still missing?

Mocking `JwtDecoder` exercises the Spring JWT filter + converter + authorization, but **skips actual signature/JWKS/issuer/audience/expiry validation**. Another integration test must use **tokens signed with a test private key** and a test decoder/JWKS endpoint to verify:
- Valid signature + issuer + audience + lifetime ⇒ resource server evaluates authorities.
- Bad signature, disallowed `alg`, wrong issuer, `aud` not for this API, expired/future `nbf` ⇒ 401.
- Valid JWT with missing/unknown/wrong-client roles ⇒ 403.
- Do not accept an OAuth2 login ID token in place of an API access token.
- Key rotation/revocation per provider contract.
- When a role is revoked, behavior depends on TTL/token freshness; if immediate revocation is required, add dedicated mechanisms.

### 10.2. Why not use `@WithMockUser(roles="ADMIN")` alone?

`@WithMockUser(roles="ADMIN")` creates a mock `Authentication` with `ROLE_ADMIN` directly. It is useful for testing **method rules** in isolation, but does not test JWT claim mapping. Converter tests should build `Jwt` fixtures; filter tests can mock `JwtDecoder`; full trust tests require signed tokens/JWKS. These three test layers serve different purposes—do not treat one as a substitute for the others.

## 11. Testing role prefixes with a practical matrix

| Source input | Desired mapping | What to assert |
| --- | --- | --- |
| `scope="reports.read"` | `SCOPE_reports.read` | Does not become `ROLE_reports.read` |
| `scp=["orders.read"]` | `SCOPE_orders.read` | Default converter preserves scoped authority |
| `roles=["ADMIN"]` | `ROLE_ADMIN` | `hasRole("ADMIN")` GRANTS |
| `roles=["ROLE_ADMIN"]` | Ignored/denied per illustrative contract | Does not create `ROLE_ROLE_ADMIN` |
| `roles=["admin"]` | Ignored/denied | Case-sensitive |
| `roles=["SUPERADMIN"]` | Ignored/denied | Allow-list |
| `roles=["ADMIN","ADMIN"]` | One `ROLE_ADMIN` | Deduplicated |
| `realm_access.roles=["AUDITOR"]` | `ROLE_AUDITOR` | Trusted realm only |
| `resource_access.orders-api.roles=["write"]` | `PERM_ORDERS_WRITE` | Not global admin |
| `resource_access.other-client.roles=["admin"]` | Ignored | No cross-client privilege |
| `roles="ADMIN"` (string) | Ignored by this converter | Does not silently parse another shape |
| `realm_access.roles=123` | Ignored | Malformed claim |
| Valid JWT with wrong audience | Decoder rejects | 401, converter never runs |
| User with role ADMIN in tenant A, request to tenant B | Tenant policy decides, not global role | No access to tenant B |
| Claim suddenly changes array→string due to IdP update | Contract test fails | Does not open up permissions silently |

A simple converter calling `setAuthorityPrefix("ROLE_")` can suffice for top-level role claims **that match the contract**, but not every OAuth2 system should use it.

## 12. OAuth2 Resource Server differs from OAuth2/OIDC Login

### 12.1. Resource Server receives Bearer access tokens

Main demo:
- The app is an **API** receiving `Authorization: Bearer <access token>`.
- `JwtDecoder` validates the token.
- `JwtAuthenticationConverter` maps JWT claims to authorities.
- Controller/method security checks `JwtAuthenticationToken`.
- No web login redirect or OAuth2 user session is required.

### 12.2. OAuth2 Login is a different pipeline

In a web app using:

~~~java
http.oauth2Login(login -> login
        .userInfoEndpoint(userInfo ->
                userInfo.userAuthoritiesMapper(myAuthoritiesMapper)));
~~~

`myAuthoritiesMapper` is a `GrantedAuthoritiesMapper` for `OAuth2User` or `OidcUser` authorities, not a bearer resource server `JwtAuthenticationConverter`. It receives `OAuth2UserAuthority`/`OidcUserAuthority` and the logged-in user's scope authorities.

OIDC roles may live in the **ID token**, UserInfo, or another backend endpoint; which source is trusted to grant app roles must be evaluated under the security/privacy contract. If you need to call a protected API to fetch roles, use a delegated `OidcUserService`/`OAuth2UserService` with a properly audience-scoped token rather than treating a frontend ID token as a resource server access token.

### 12.3. Snippet-style OIDC mapper example

~~~java
// Inside oauth2Login configuration, distinct from Resource Server JWT.
// Illustrates shape only; issuer/claim policy checks must be added.
GrantedAuthoritiesMapper mapper = input -> {
    Set<GrantedAuthority> output =
            new LinkedHashSet<>(input);

    for (GrantedAuthority authority : input) {
        if (authority instanceof OidcUserAuthority oidc) {
            Object raw = oidc.getIdToken().getClaims().get("roles");
            if (raw instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if ("VIEWER".equals(item)) {
                        output.add(new SimpleGrantedAuthority(
                                "ROLE_VIEWER"));
                    }
                }
            }
        }
    }
    return output;
};
~~~

This is a snippet meant for a Java method with imports for `GrantedAuthoritiesMapper`, `GrantedAuthority`, `OidcUserAuthority`, `LinkedHashSet`, `Set`, `Collection`, and `SimpleGrantedAuthority`. Do not paste it into the main Resource Server file expecting it to auto-wire. Specifically, an OIDC `ID token` is issued for the client to authenticate the end user, not as a standard bearer access token to call arbitrary resource servers.

## 13. Reactive WebFlux: same policy, different converter

In a WebFlux Resource Server, use `ReactiveJwtAuthenticationConverter` instead of injecting a Servlet `JwtAuthenticationConverter` into the reactive DSL. For the synchronous non-blocking converter from Section 7, use the adapter:

~~~java
// Snippet inside a Spring Security 6.5 WebFlux @Bean config:
ReactiveJwtAuthenticationConverter reactive =
        new ReactiveJwtAuthenticationConverter();

reactive.setJwtGrantedAuthoritiesConverter(
        new ReactiveJwtGrantedAuthoritiesConverterAdapter(
                new ScopesAndRolesConverter()));

// In ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)
// use reactive.jwtAuthenticationConverter(reactive).
~~~

The adapter takes `Converter<Jwt, Collection<GrantedAuthority>>` and exposes `Converter<Jwt, Flux<GrantedAuthority>>`; the underlying converter must be **non-blocking**. `ScopesAndRolesConverter` only maps Maps, Lists, and strings, so it is suitable; if network/DB PIP lookups are required, use a reactive converter/service with timeouts and fail-closed handling—never call `block()` inside the pipeline.

Do not confuse WebFlux HTTP `hasRole` with method SpEL or a custom `ReactiveAuthorizationManager`; by default, `ROLE_ADMIN` remains the required authority when calling `hasRole("ADMIN")`. Re-verify in both HTTP and method tests whenever versions or prefix configs change.

## 14. Tenant roles, global admin, and business data

A JWT with `roles=["ADMIN"]` might mean:
- Administrator of the entire **realm**, without permission to modify every tenant's data.
- Administrator of a single client (with different meaning per application).
- Administrator of a specific tenant in a multi-tenant system.
- A technical role solely for accessing an IdP dashboard, not a business permission.

If you map all of these into a global `ROLE_ADMIN` and put `hasRole("ADMIN")` on every data endpoint, **horizontal privilege escalation** can occur. Never use a role name as a substitute for tenant membership and object ACLs.

Document protection example:
1. Validate the JWT for the right issuer/audience.
2. The converter can map `ROLE_EDITOR`.
3. A request asks for `PATCH /tenants/beta/documents/7`.
4. The service verifies the actor holds EDITOR membership in **beta**, not merely EDITOR in alpha.
5. The DB query/update includes `tenant_id=beta AND id=7`, checking owner/ACL/classification per policy.
6. If permission is revoked between check and write, enforce freshness/transaction/version guards.

Never cache `ALLOW` keyed solely by `documentId` or `ROLE_ADMIN`. Cache keys/policies must distinguish principal, tenant, action, resource, and the relevant ACL/membership/policy revision. For sensitive permissions, avoid caching ALLOW or revalidate within SLA.

### 14.1. Never put a caller-supplied `tenantId` into a role authority without verification

Anti-pattern:

~~~java
String tenant = request.getHeader("X-Tenant");
authorities.add(new SimpleGrantedAuthority(
        "ROLE_" + tenant + "_ADMIN"));
~~~

Headers can be forged. If implementing a tenant-scoped authority namespace, the tenant must come from a trusted membership source/verified claim, and checks must remain resource-scoped; concatenating an authority name creates no authenticity.

### 14.2. Role hierarchy and scope

If you configure `ROLE_ADMIN > ROLE_EDITOR > ROLE_VIEWER` via a role hierarchy, an ADMIN inherits multiple authorities wherever that hierarchy applies. While convenient, it expands the privilege surface. Do not enable a global hierarchy across realm/tenant/client roles unless the business requires it. Verify that the role hierarchy is actually wired into the method/HTTP authorization managers you use; never assume every method automatically knows about the hierarchy.

## 15. Revocation, token staleness, and policy changes

Signed JWT access tokens are typically self-contained. If Alice's ADMIN role is removed after the token was issued, the API may still see the ADMIN claim until the token expires unless the architecture adds mechanisms such as:
- Short-lived access tokens and refresh token rotation.
- Token introspection/reference tokens or a revocation list in the resource server when near-real-time revocation is needed.
- Server-side membership/role revision checks against a trusted PIP.
- Event-driven cache invalidation and monitoring.
- Session invalidation for web OAuth2 Login (which is not the same as revoking a JWT access token).
- Combining policy version/ACL checks for sensitive operations.

Never claim "removing a role in the IdP revokes API access immediately" when using JWTs without a revocation lookup. Balance latency/availability against the revocation SLA, with negative tests proving the chosen behavior.

## 16. Logging controls and common security pitfalls

### 16.1. Never log full JWTs for debugging

JWTs can contain names, emails, tenants, roles, device data, or internal IDs. Even though base64URL payloads are trivial to decode, token headers/bodies are sensitive, and raw bearer tokens are live credentials. Log minimally:
- Request ID, normalized issuer identifier, opaque subject (if policy allows), 401/403 outcome, endpoint/action, and redacted authority categories.
- Never log Authorization headers, raw JWTs, refresh tokens, private keys/JWKS secrets, or full claim sets.
- Debug mappings in test environments using fixture tokens, not by printing full authorities of production users.

### 16.2. Common mistakes

1. **JWT has `roles=["ADMIN"]`, yet Spring still returns 403:** Resource Server maps scopes to `SCOPE_*` by default; the role claim is not mapped yet.
2. **`hasRole("ROLE_ADMIN")`:** passing an already-prefixed role can double-prefix or be rejected; use `hasRole("ADMIN")`.
3. **`hasAuthority("ADMIN")` against `ROLE_ADMIN`:** does not match; use the exact full string.
4. **`ROLE_ROLE_ADMIN`:** IdP already prefixed it and the converter prefixes again; standardize the raw role schema.
5. **Using `setAuthorityPrefix("ROLE_")` on the scope claim:** turns OAuth2 scopes into business roles without security review.
6. **Switching the claim name to `roles` alone:** drops `SCOPE_*` unless converters are combined.
7. **`setAuthoritiesClaimName("realm_access.roles")`:** does not read nested paths; requires custom `Map` traversal.
8. **Mapping all roles across `resource_access`:** another client's roles accidentally grant privileges in `orders-api`.
9. **No role allow-list:** typos, unknown roles, or colliding names can produce unexpected authorities.
10. **Trusting roles from headers/body/unsigned JWTs:** unverified tokens or client-asserted claims.
11. **Checking only issuer while forgetting audience:** tokens issued for another service get accepted.
12. **Using an ID token as an API Bearer access token:** wrong token purpose and audience.
13. **Checking only a global role on tenant-specific objects:** fails to replace membership/ACL/DB scoping.
14. **Testing `jwt().authorities(...)` and assuming the mapper works:** the test bypassed the converter.
15. **Mocking `JwtDecoder` and claiming signature validation is tested:** it is not; signed token/JWKS integration tests are needed.
16. **Changing `GrantedAuthorityDefaults` and assuming the whole app aligns:** HTTP/method/custom managers may have different prefix semantics.
17. **Mapping roles with `contains("ADMIN")`:** `SUPERADMIN` or comment strings can match erroneously.
18. **Treating upper/lowercase as equivalent:** Spring authority strings are case-sensitive.
19. **Caching ALLOW long-term despite revoked roles:** stale JWT/ACL; needs a revocation strategy.
20. **Mixing Servlet `JwtAuthenticationConverter` with WebFlux `ReactiveJwtAuthenticationConverter`:** incompatible pipelines.
21. **Missing `@EnableMethodSecurity`:** `@PreAuthorize` may not execute; test through real proxies/services.
22. **Leaving endpoints as `anyRequest().authenticated()` without specific checks:** a valid JWT does not imply object permissions.
23. **Reading roles from an issuer not in the trust allow-list:** mapping from untrusted data.
24. **Reading UserInfo scopes to grant global admin:** scopes represent OAuth client delegation, not admin identity.
25. **Failing to test malformed role arrays/maps:** converter may throw 500 or fail open in custom exception paths.

## 17. Production deployment checklist

| Area | Must verify |
| --- | --- |
| Token type | Access token meant for resource server, not confused with OIDC ID token |
| Signature | JWS verified, trusted algorithms/JWKS/keys |
| Issuer | `iss` restricted to trusted realms/IdPs |
| Audience | `aud` matches `orders-api`/resource |
| Lifecycle | `exp`/`nbf`/clock skew, revocation SLA |
| Default scopes | `scope`/`scp` continue mapping to `SCOPE_*` |
| Role sources | Approved claims only, exact nested paths |
| Prefix | Single `ROLE_`, no `ROLE_ROLE_ADMIN` |
| Role allow-list | `ADMIN`/`EDITOR`/`VIEWER`/`AUDITOR` or formal contract |
| Client isolation | Never pull roles from arbitrary `resource_access` clients |
| Tenant | Verify membership and DB resource scope independently |
| Method security | `@EnableMethodSecurity` and proxy invocation |
| HTTP security | Consistent `hasRole("ADMIN")`/`hasAuthority(...)` |
| Unknown roles | Never synthesize admin authorities from unknown values |
| Malformed claims | Grant no authorities when types are wrong |
| OAuth2 Login | Separate mapper/UserService if web login exists |
| WebFlux | Use `ReactiveJwtAuthenticationConverter`/non-blocking adapter |
| Negative tests | 401 invalid JWT, 403 valid/no roles, prefix mismatch |
| Mapping tests | Converter unit tests + filter integration + signed JWT/JWKS |
| Monitoring | 401/403 metrics, mapping drift, provider schema changes |
| Logging | No raw JWTs/PII/secrets; safe tracing |
| Operations | Short-lived tokens, key rotation, role revocation plan |

### 17.1. Mutation tests to prove the test suite catches regressions

Intentionally break one branch in a test run:
- Remove `roles` mapping → `approvedRoleMatchesHasRole` must fail.
- Remove the scope delegate → `scopesSurviveRoleMapping` must fail.
- Map client role `write` to `ROLE_ADMIN` → `unrelatedClientRoleDoesNotGrant` and negative role tests must catch the flawed design (add a test verifying client role `write` never produces ADMIN).
- Accept pre-prefixed `ROLE_ADMIN` by prepending `ROLE_` → the double-prefix test must fail.
- Remove `@EnableMethodSecurity` → `/api/orders/check` could return 200 for viewer; tests must fail.
- Remove audience validation in the production decoder → signed wrong-audience test must fail.
- Remove the tenant predicate from repository queries → cross-tenant object tests must fail.

A suite with only a single 200 happy path cannot prove role mapping is secure.

## 18. Standalone Java 17: prefix mapping and decisions without Spring

The following program runs on **plain JDK 17** and models the exact chosen mapping policy: keep scopes separate, accept only allow-listed roles from known claim structures, map client permissions by app name, and never double-prefix. It **does not implement signature/JWT verification, Spring `SecurityFilterChain`, OAuth2 Login, or Reactor**.

Save as `RolePrefixDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class RolePrefixDemo {
    record Token(List<String> roles, List<String> scopes,
                 Map<String, List<String>> clientRoles) {}

    private static final Set<String> ALLOWED_GLOBAL =
            Set.of("ADMIN", "EDITOR", "VIEWER", "AUDITOR");

    static Set<String> authorities(Token token) {
        Set<String> result = new TreeSet<>();

        for (String scope : token.scopes()) {
            if (scope != null && !scope.isBlank()) {
                result.add("SCOPE_" + scope);
            }
        }

        for (String role : token.roles()) {
            if (ALLOWED_GLOBAL.contains(role)) {
                result.add("ROLE_" + role);
            }
        }

        for (String role : token.clientRoles()
                                .getOrDefault("orders-api", List.of())) {
            if ("read".equals(role)) {
                result.add("PERM_ORDERS_READ");
            }
            if ("write".equals(role)) {
                result.add("PERM_ORDERS_WRITE");
            }
        }
        return result;
    }

    static boolean hasRole(Set<String> a, String role) {
        return a.contains("ROLE_" + role);
    }

    static boolean hasAuthority(Set<String> a, String exact) {
        return a.contains(exact);
    }

    public static void main(String[] args) {
        Token admin = new Token(
                List.of("ADMIN", "ROLE_ADMIN"),
                List.of("reports.read"),
                Map.of("orders-api", List.of("write")));

        Token viewer = new Token(
                List.of("VIEWER"),
                List.of("reports.read"),
                Map.of("other-client", List.of("admin")));

        Token invalid = new Token(
                List.of("ROLE_ADMIN", "SUPERADMIN", "admin"),
                List.of(),
                Map.of("orders-api", List.of("unexpected")));

        Set<String> a = authorities(admin);
        Set<String> v = authorities(viewer);
        Set<String> x = authorities(invalid);

        System.out.println("admin-authorities=" + a);
        System.out.println("admin-hasRole-ADMIN=" +
                hasRole(a, "ADMIN"));
        System.out.println("admin-hasAuthority-ADMIN=" +
                hasAuthority(a, "ADMIN"));
        System.out.println("admin-hasAuthority-ROLE_ADMIN=" +
                hasAuthority(a, "ROLE_ADMIN"));
        System.out.println("admin-orders-write=" +
                hasAuthority(a, "PERM_ORDERS_WRITE"));
        System.out.println("viewer-authorities=" + v);
        System.out.println("viewer-hasRole-ADMIN=" +
                hasRole(v, "ADMIN"));
        System.out.println("viewer-hasScope-reports=" +
                hasAuthority(v, "SCOPE_reports.read"));
        System.out.println("invalid-authorities=" + x);
        System.out.println("invalid-hasRole-ADMIN=" +
                hasRole(x, "ADMIN"));
    }
}
~~~

Commands:

~~~bash
javac --release 17 RolePrefixDemo.java
java RolePrefixDemo
~~~

**Exact stdout** (`TreeSet` ensures deterministic order):

~~~text
admin-authorities=[PERM_ORDERS_WRITE, ROLE_ADMIN, SCOPE_reports.read]
admin-hasRole-ADMIN=true
admin-hasAuthority-ADMIN=false
admin-hasAuthority-ROLE_ADMIN=true
admin-orders-write=true
viewer-authorities=[ROLE_VIEWER, SCOPE_reports.read]
viewer-hasRole-ADMIN=false
viewer-hasScope-reports=true
invalid-authorities=[]
invalid-hasRole-ADMIN=false
~~~

Exercise: adding `ADMIN` to `other-client` without placing it in `roles` must not produce `ROLE_ADMIN`. Adding `ROLE_ADMIN` to `roles` without `ADMIN` must DENY admin under this contract. If you modify the code to turn every `scope` into `ROLE_`, ask yourself who is actually authorized to issue the ADMIN role.

**Limitation:** this is a Java string simulation and does not prove token signature/audience validation or Spring's authority mapping. Spring classes must be tested via converter and HTTP filter tests as shown in Sections 9–10.

## 19. Self-check questions

**Question 1.** A token has `scope="admin"` and no role claim. Should you use `setAuthorityPrefix("ROLE_")` so `hasRole("ADMIN")` succeeds?

**Answer:** Not by default. Scopes are OAuth client authorization grants, not the same namespace or issuance rules as business roles. There must be an explicitly approved issuer/audience/scope→role policy; it is safer to keep `SCOPE_admin` for scopes and issue `ROLE_ADMIN` only from a trusted role source.

**Question 2.** The IdP returns `roles=["ROLE_ADMIN"]` while the converter prefixes `ROLE_`. Will an app checking `hasRole("ADMIN")` grant access?

**Answer:** No, because of the double prefix `ROLE_ROLE_ADMIN`. Fix the contract at the IdP or converter; do not alter matchers to accept unexpected malformed values.

**Question 3.** Why does `setAuthoritiesClaimName("realm_access.roles")` usually fail to work?

**Answer:** It selects a top-level claim name and does not parse nested JSON automatically. You must traverse the `realm_access` map and read the `roles` list, restricting both role names and issuer.

**Question 4.** After replacing the converter to read only roles, why does an API previously requiring `SCOPE_orders.read` start returning 403?

**Answer:** The default scope mapper was replaced. You must delegate/combine both sources into a single authority collection rather than replacing everything with roles.

**Question 5.** A Resource Server receives a token with a valid issuer and role ADMIN, but its audience targets a different service. Should ADMIN be mapped?

**Answer:** No; the decoder/validator must reject wrong-audience tokens before role mapping runs. A valid issuer does not make a token valid for every API.

**Question 6.** Does `jwt().authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` in a MockMvc test prove the real mapper works?

**Answer:** No. That test injects authorities manually. Only converter unit tests and resource-server tests with a mocked decoder or signed JWT verify the mapping.

**Question 7.** A JWT contains `resource_access.other-client.roles=["admin"]`. Should `orders-api` turn that into global `ROLE_ADMIN`?

**Answer:** No. That role belongs to another client's namespace; map only approved client apps per the security contract rather than iterating over all clients.

**Question 8.** Why is `ROLE_ADMIN` in the token insufficient for `GET /tenants/beta/documents/7`?

**Answer:** A global or realm admin role does not prove membership in tenant beta or object permissions. The service must still verify tenant/action/ACL and query by trusted tenant.

**Question 9.** If a user's role was removed at the IdP, why might the API still allow access for a few minutes?

**Answer:** Self-contained access tokens still carry the old claims until expiration; earlier revocation requires short TTLs, role revisions, introspection, or revocation checks aligned with your SLA.

**Question 10.** Why does a converter need an allow-list instead of blindly mapping every string in `roles`?

**Answer:** It mitigates risks from new unexpected IdP roles, case/schema mismatches, namespace collisions, other clients' roles, or invalid strings turning into elevated privileges. Map only roles whose semantics are agreed upon by both provider and API.

## 20. Conclusion

Treat role claim mapping as a **two-way security contract**, not mere string concatenation:

~~~text
Trusted access token
    -> signature/issuer/audience/expiry validated by JwtDecoder
    -> parse approved claims and exact shapes
       -> OAuth scopes             => SCOPE_...
       -> approved global roles    => ROLE_...
       -> approved client roles    => PERM_...
    -> JwtAuthenticationToken authorities
    -> hasRole("ADMIN") or hasAuthority("ROLE_ADMIN")
    -> tenant/resource/action authorization
    -> protected operation and audit
~~~

Three key takeaways:

- **Create `ROLE_` strictly once and check it accurately.** `hasRole("ADMIN")` and `hasAuthority("ROLE_ADMIN")` both target `ROLE_ADMIN` in default config; `hasAuthority("ADMIN")` is not equivalent.
- **Never turn scopes or another client's roles into global admin.** Preserve `SCOPE_*` where policies rely on it, and map `ROLE_*` using an allow-list plus issuer/audience/client boundaries.
- **Token mapping is only one layer.** The JWT must be verified; OAuth2 Login and Resource Server use different converters; multi-tenant roles/ACLs, revocation, proxy/method security, and DB scoping must still be enforced.

If a wrong-audience token, a `roles=["ROLE_ADMIN"]` claim, or an `admin` role limited to `other-client` can still call `/api/admin` on `orders-api`, the mapping design is not secure yet.

## Official references

- [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT validation, `SCOPE_`, `JwtAuthenticationConverter`, custom claim/prefix, and audience.
- [Spring Security 6.5 – JwtGrantedAuthoritiesConverter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): `setAuthoritiesClaimName`, `setAuthorityPrefix`, `setAuthoritiesClaimDelimiter`.
- [Spring Security 6.5 – JwtAuthenticationConverter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): `setJwtGrantedAuthoritiesConverter`, `setPrincipalClaimName`.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasRole`/`hasAuthority` and matcher semantics.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority` and role prefix.
- [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `GrantedAuthoritiesMapper`, `OidcUserAuthority`, delegated user service.
- [Spring Security 6.5 – ReactiveJwtAuthenticationConverter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverter.html): reactive converter contract.
- [Spring Security 6.5 – ReactiveJwtGrantedAuthoritiesConverterAdapter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtGrantedAuthoritiesConverterAdapter.html): adapter between sync collection and reactive Flux.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
