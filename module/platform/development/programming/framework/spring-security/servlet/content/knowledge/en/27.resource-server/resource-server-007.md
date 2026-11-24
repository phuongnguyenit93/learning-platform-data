# Resource Server: Mapping Scopes to Authorities and Customizing Permission Claims in Spring Security Servlet

## 1. Goal: From Access Token to Allow or Deny Decision

An **OAuth2 Resource Server** is an API that receives an **access token** (typically sent via `Authorization: Bearer ...`), verifies the token, and decides whether the caller can access a resource. In a **Spring Boot 3.x + Spring Security 6.x, Servlet/Spring MVC, Java 17+** application, this decision typically uses **`GrantedAuthority`** instances attached to `Authentication`.

This lesson focuses on two tasks:

1. Understanding and using the default mapping from scopes in an access token to authorities prefixed with **`SCOPE_`**.
2. When an IdP emits additional claims containing roles or business permissions, writing a **custom converter** to turn trusted claims into authorities like `ROLE_ADMIN` and `PERM_orders:approve`, and checking permissions properly at URL and method levels.

Clearly distinguish:

- **Scope**: capability range granted to the token/client, e.g., `orders:read`, `orders:write`. A scope is not automatically equivalent to a user role.
- **Role**: a subject's role within a context, e.g., `ADMIN`, `SUPPORT`; usually prefixed with `ROLE_` when using `hasRole`.
- **Permission**: a specific business privilege, e.g., `orders:approve`; can be mapped to `PERM_orders:approve`.
- **Claim**: a data field inside a JWT, such as `scope`, `scp`, `sub`, `aud`, `realm_access`, `permissions`. A claim is trusted **only after the token is verified valid** and in the right API context.

**Never turn an arbitrary string supplied by a request header/query/body into an authority.** Authorities must originate from a verified token, a trusted permission store, or a controlled authorization decision.

## 2. Processing Flow in Spring Security Servlet

With a JWT Bearer access token, the typical processing flow:

```text
HTTP GET /api/orders
  Authorization: Bearer eyJ...

        |
        v
BearerTokenAuthenticationFilter
        |
        v
JwtDecoder
  - verify signature using appropriate key (JWK)
  - verify expiration and issuer (iss)
  - verify audience (aud) if configured
  - additional business validators
        |
        v
JwtAuthenticationConverter
  - read scope / scp
  - read trusted roles / permissions claims
  - build Collection<GrantedAuthority>
        |
        v
JwtAuthenticationToken in SecurityContext
        |
        v
AuthorizationFilter / method security
  - hasAuthority("SCOPE_orders:read")
  - hasRole("ADMIN") ~ requires ROLE_ADMIN
  - hasAuthority("PERM_orders:approve")
        |
        v
Controller / service (if permitted)
```

Each step has its own responsibility. **`JwtDecoder`/validators verify the token's validity and target; the converter maps verified data into authorities; the authorization policy decides which endpoint needs which authority.** Changing the converter does not make an improperly signed token valid and does not add `aud` checks automatically.

Depending on token format, a Resource Server can also use **opaque token introspection** instead of JWTs. In that case `JwtAuthenticationConverter` does not run; authority customization must be applied in the corresponding introspection flow (see section 12).

## 3. Default: `scope`/`scp` → `SCOPE_...`

Spring Security Resource Server JWT uses `JwtGrantedAuthoritiesConverter` by default to look up common scope claims (`scope`, `scp`). It reads scope values and creates `SimpleGrantedAuthority` instances prefixed with **`SCOPE_`**.

Illustrative JWT payload (decoded for learning; **not a validly signed JWT**):

```json
{
  "iss": "https://idp.example.test/realms/learning",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders:read orders:write"
}
```

Two space-separated scopes yield two authorities:

```text
SCOPE_orders:read
SCOPE_orders:write
```

Another provider might use an array:

```json
{
  "sub": "user-42",
  "scp": ["orders:read", "orders:write"]
}
```

Crucially, the default converter reads **one** matching scope claim according to internal precedence—do not assume it automatically merges both `scope` and `scp` if both exist. Agree on a claim contract with your IdP. If the token uses another claim name, configure `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName(...)`.

### 3.1. Using `hasAuthority` and `hasRole` Properly

| Actual Authority in Authentication | Correct Condition | Wrong or Easily Confused Condition |
| --- | --- | --- |
| `SCOPE_orders:read` | `hasAuthority("SCOPE_orders:read")` | `hasRole("orders:read")` |
| `SCOPE_orders:write` | `hasAuthority("SCOPE_orders:write")` | `hasAuthority("orders:write")` |
| `ROLE_ADMIN` | `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` | `hasRole("ROLE_ADMIN")` under default usage |
| `PERM_orders:approve` | `hasAuthority("PERM_orders:approve")` | `hasRole("orders:approve")` |

In typical configurations, `hasRole("ADMIN")` checks for **`ROLE_ADMIN`**; whereas `hasAuthority("...")` matches **the exact authority string**. The prefix configured in the converter and the authorization expression must stay consistent. Avoid changing the `SCOPE_` prefix to `ROLE_` if scopes do not actually represent roles.

### 3.2. When You Only Need to Rename the Claim or Prefix

If the API only needs a `permissions` claim holding a permission list, a simple scope converter may suffice:

```java
JwtGrantedAuthoritiesConverter custom = new JwtGrantedAuthoritiesConverter();
custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(custom);
```

**Note:** this replacement makes the converter read `permissions` instead of automatically preserving **both** default `scope` values. If you need to **combine scope + role + permission**, use a combined converter as in section 7. Starting in Spring Security 6.1, `setAuthoritiesClaimDelimiter(...)` can also customize how string claims are split; do not rely on that API when targeting 6.0.

## 4. Roles and Permissions Claims Have No Single Standard Across All IdPs

An illustrative token might contain:

```json
{
  "iss": "https://idp.example.test/realms/learning",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read orders:write",
  "realm_access": {
    "roles": ["ADMIN", "SUPPORT"]
  },
  "permissions": ["orders:approve", "orders:refund"]
}
```

In this example, the application wants to map them to:

```text
SCOPE_orders:read
SCOPE_orders:write
ROLE_ADMIN
ROLE_SUPPORT
PERM_orders:approve
PERM_orders:refund
```

**This is a claim contract agreed between the application and IdP, not a mandatory OAuth2 token format.** One IdP may use `roles`, `groups`, `realm_access.roles`, `resource_access.<client>.roles`, `permissions`, or emit only scopes. Never blindly apply IdP A's schema to IdP B.

Besides claim names, clarify the **effective scope** of roles. `realm_access.roles` may be realm-wide roles shared across many applications. If you only want roles scoped to `orders-api`, a safer choice may be an API-specific claim or resource/client-scoped roles (`resource_access`) combined with an audience check, rather than granting every global role to every API.

### 4.1. Why Is a Whitelist Needed?

Suppose the IdP adds a `SUPERUSER` role in the future. If a default converter turns every string into `ROLE_`, a new policy or mistyped policy could inadvertently grant excessive privileges. Therefore, the example converter below accepts only roles/permissions in a list recognized by the application.

A whitelist controls **permission names** but is **insufficient** if issuer/audience are unverified. Roles/permissions must also be issued by an IdP authoritative for that API; in multi-tenant setups, bind roles/permissions to their corresponding tenant/resource.

### 4.2. A Properly Signed JWT May Still Be Unusable for This API

A JWT may have a valid signature yet:

- `iss` is a different issuer from the one trusted by the API.
- `aud` does not include the Resource Server's audience.
- `exp` is expired or `nbf` is in the future.
- It is an **ID Token** issued to an OAuth2 Client for login, not an access token issued for the API.
- It carries a `roles` claim issued for another application, meaningless for authorization on the current API.

Therefore, separate **validity** (signature, timestamps, issuer), **intended recipient** (audience, token type where needed), and **authorization** (scope/role/permission). Converting claim names to authorities must never bypass any of those steps.

## 5. Policy Design: Scope, Role, or Permission?

Example order management API:

| Action | Suggested Policy | Rationale |
| --- | --- | --- |
| `GET /api/orders` | `SCOPE_orders:read` | Token was granted read scope |
| `POST /api/orders/approve` | `PERM_orders:approve` | Approval privilege is a business permission, not just broad access |
| `GET /api/admin/audit` | `ROLE_ADMIN` | Only administrative staff may access |
| `GET /api/me` | Authenticated caller | View authenticated principal info; no special business scope needed |

Not every system needs all three layers; many APIs work fine with scopes alone. If used together, document **which role holds which business permissions**, who issues the tokens, and when they are revoked. Never assume `ADMIN` automatically implies every scope: if policy requires both scope and role, use an **AND** expression or an explicit AuthorizationManager.

**Distinguish URL protection from data protection:** holding `orders:read` does not mean a user can read **every** order. Data must still be filtered by tenant, owner, status, or row-level/object-level authorization rules. A user with `ROLE_SUPPORT` in tenant A must not automatically act on tenant B.

## 6. Illustrative Spring Boot 3.x / Java 17+ Project

The complete example below is a **pure JWT Resource Server**, with no login form or cookie session. The API reads Bearer access tokens, verifies issuer/audience/JWK, builds scopes + roles + permissions, and checks authorization at endpoints. It runs when paired with a **real IdP issuing compatible JWT access tokens**; `idp.example.test` is illustrative, not a live service.

### 6.1. Gradle Dependencies

Create a Spring Boot 3.x Java 17 project with the following dependencies in `build.gradle` (Groovy DSL). Plugins, versions, and dependency management are generated by Spring Initializr:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Do not add the OAuth2 Client starter merely for an API to verify Bearer tokens. An **OAuth2 Client** acquires/holds tokens to call APIs or log users in; a **Resource Server** receives and verifies access tokens. One application can play both roles, but the filters and responsibilities differ.

### 6.2. `application.yml`

File `src/main/resources/application.yml`:

```yaml
app:
  security:
    jwt:
      issuer: https://idp.example.test/realms/learning
      jwk-set-uri: https://idp.example.test/realms/learning/protocol/openid-connect/certs
      audience: orders-api
```

Replace the URLs and audience for your real IdP. In this example, `JwtDecoder` is created explicitly in section 8 to verify both issuer and audience simultaneously. If you only configure `spring.security.oauth2.resourceserver.jwt.issuer-uri` without an audience validator, do not assume every token from the same issuer should be accepted by the API.

In production, the JWK endpoint must be served over HTTPS; control network trust, key caching/rotation, and IdP unreachability handling. Never disable signature verification to test a converter.

### 6.3. Main Class

File `src/main/java/com/example/orders/OrdersResourceServerApplication.java`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersResourceServerApplication.class, args);
    }
}
```

## 7. Combined Converter: Preserving Default Scopes and Adding Permission Claims

File **`src/main/java/com/example/orders/ApiAuthoritiesConverter.java`**:

```java
package com.example.orders;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class ApiAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final Set<String> TRUSTED_ROLES =
        Set.of("ADMIN", "SUPPORT");

    private static final Set<String> TRUSTED_PERMISSIONS =
        Set.of("orders:approve", "orders:refund");

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();

        // 1. Preserve default Spring Security behavior: scope/scp -> SCOPE_...
        Collection<GrantedAuthority> scopeAuthorities = scopes.convert(jwt);
        if (scopeAuthorities != null) {
            result.addAll(scopeAuthorities);
        }

        // 2. Read the realm_access.roles structure when specified by the IdP.
        Object realmAccessClaim = jwt.getClaim("realm_access");
        if (realmAccessClaim instanceof Map<?, ?> realmAccess) {
            Object rolesClaim = realmAccess.get("roles");
            if (rolesClaim instanceof Collection<?> roles) {
                for (Object rawRole : roles) {
                    if (rawRole instanceof String role
                            && TRUSTED_ROLES.contains(role)) {
                        result.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }
        }

        // 3. Business permissions use a distinct prefix, avoiding confusion with roles.
        Object permissionsClaim = jwt.getClaim("permissions");
        if (permissionsClaim instanceof Collection<?> permissions) {
            for (Object rawPermission : permissions) {
                if (rawPermission instanceof String permission
                        && TRUSTED_PERMISSIONS.contains(permission)) {
                    result.add(new SimpleGrantedAuthority(
                        "PERM_" + permission));
                }
            }
        }

        return result;
    }
}
```

### 7.1. Why Does This Implementation Make Those Choices?

- Uses `JwtGrantedAuthoritiesConverter` instead of hand-parsing scopes, because Spring's converter already handles standard scope claims and the `SCOPE_` prefix.
- Uses `LinkedHashSet` to deduplicate authorities and preserve relatively stable ordering; **authority ordering does not determine access**.
- Checks `Map`, `Collection`, and `String` types before reading claims. If an IdP emits a claim violating the contract, arbitrary objects are not turned into permission names.
- Emits only `ROLE_ADMIN`, `ROLE_SUPPORT`, and the two registered business permissions. To add another role, update the whitelist **alongside policies and tests**.
- The `PERM_` prefix separates business permissions from scopes and roles, making authorization expressions harder to misread.
- Never adds authorities from `sub`, `email`, username, HTTP headers, or arbitrary group names without analyzing their source and trust boundary.

**The claim contract must be explicit.** If the IdP emits `roles: ["admin"]` (lowercase) instead of `realm_access.roles: ["ADMIN"]`, this converter **will not** assign `ROLE_ADMIN`. Adjust the extractor to match the real IdP format and write corresponding tests; avoid calling `toUpperCase()` on arbitrary strings to “guess” a privileged role.

### 7.2. If Roles Reside in `resource_access.<client>.roles`

Some IdPs distinguish realm roles from client/resource roles. Example:

```json
{
  "resource_access": {
    "orders-api": {
      "roles": ["SUPPORT"]
    },
    "unrelated-client": {
      "roles": ["ADMIN"]
    }
  }
}
```

If the Resource Server's policy only uses roles intended for `orders-api`, read **the `resource_access.orders-api.roles` branch**—do not scan every branch and do not accept `ADMIN` from `unrelated-client`. Pick **one role contract**: if switching to resource roles, replace the `realm_access` lookup in the converter with type-checked nested map access; do not combine both sources without a clear authorization reason. Audience validation remains mandatory.

## 8. Protecting Endpoints and Validating JWTs

File **`src/main/java/com/example/orders/SecurityConfig.java`**:

```java
package com.example.orders;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
            new ApiAuthoritiesConverter());
        return converter;
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> issuerAndLifetime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> requiredAudience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                audiences -> audiences != null
                    && audiences.contains(audience));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            issuerAndLifetime, requiredAudience));

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter converter) throws Exception {

        http
            // API-only application example: Bearer token only, no cookie auth.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/approve")
                    .hasAuthority("PERM_orders:approve")
                .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(converter)
            ));

        return http.build();
    }
}
```

Points to read carefully:

1. **`JwtDecoder` is not an authority converter**. It verifies the signature against JWKS, timestamps/issuer, and **the `orders-api` audience** before handing the decoded JWT to the authentication mechanism.
2. **`JwtAuthenticationConverter`** accepts a `Converter<Jwt, Collection<GrantedAuthority>>`, here `ApiAuthoritiesConverter`, to combine the three authority groups.
3. **`hasAuthority("SCOPE_orders:read")`** checks the scope produced by the default converter, while **`hasRole("ADMIN")`** checks `ROLE_ADMIN`, and **`hasAuthority("PERM_orders:approve")`** checks the business permission.
4. **`anyRequest().denyAll()`** is a default-deny principle for endpoints not declared in the policy.
5. `.csrf(AbstractHttpConfigurer::disable)` in this example **is only appropriate for an API-only setup using Bearer tokens in headers with no reliance on auto-sent cookies**. If the app combines form login/session cookies, do not copy global CSRF disabling; design a dedicated SecurityFilterChain for `/api/**` and keep CSRF on cookie-backed areas.
6. `SessionCreationPolicy.STATELESS` ensures the Resource Server does not create or use sessions to store SecurityContext for API requests; it **does not validate** tokens itself and does not replace cookie/CSRF policies where other mechanisms exist.
7. `aud` must match the recipient API, not merely a frontend OAuth2 client. An ID Token whose audience is the login client does not become a valid API access token just because the `sub` claim exists.

**Regarding `JwtClaimValidator<List<String>>`:** standard JWT audiences can be a string or an array, though Spring's JWT decoder typically normalizes the `aud` claim into a `List<String>`. If using another decoder or custom claim mapping, verify the runtime type and write tests for both single-value and multi-value `aud`; never omit the validator to avoid type issues.

### 8.1. Controller to Observe Mapped Authorities

File **`src/main/java/com/example/orders/OrdersController.java`**:

```java
package com.example.orders;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/orders")
    public Map<String, String> orders() {
        return Map.of("result", "orders-visible");
    }

    @PostMapping("/api/orders/approve")
    @PreAuthorize("hasAuthority('PERM_orders:approve')")
    public Map<String, String> approve() {
        return Map.of("result", "approved");
    }

    @GetMapping("/api/admin/audit")
    public Map<String, String> audit() {
        return Map.of("result", "audit-visible");
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "subject", authentication.getName(),
            "authorities", authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList()
        );
    }
}
```

Because `@EnableMethodSecurity` is enabled, `@PreAuthorize` adds a second layer protecting `approve`. In larger applications, method security rules should live on business services invoked by every entry point, reducing the chance of another controller bypassing an endpoint policy.

**`/api/me` is a diagnostic demo endpoint**: it returns the authority list so you can observe the mapping in action. In production, do not necessarily expose all internal authorities to every client; return such content only when product requirements justify it and with appropriate information controls.

### 8.2. Running the Project and Calling the API

In a Gradle project with the Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`.

Once you have a **real JWT access token**, signed by the IdP with matching `iss`, `aud=orders-api`, and `exp`:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/orders
```

`ACCESS_TOKEN` is a shell environment variable holding a JWT issued by a test IdP. This illustrates Bash syntax; on PowerShell use `$env:ACCESS_TOKEN` with corresponding string interpolation.

**Expected outcomes depending on token and configuration:**

- Missing or invalid token → typically **401 Unauthorized**.
- Valid token lacking `SCOPE_orders:read` → **403 Forbidden**.
- Valid token with `orders:read` → **200 OK** with JSON `{"result":"orders-visible"}`.
- Calling `POST /api/orders/approve` requires `PERM_orders:approve`; merely having scope `orders:write` **does not allow approving orders**.
- `/api/admin/audit` requires `ROLE_ADMIN`, meaning the token must carry a role accepted by the converter.

Actual HTTP statuses also depend on exception handling, proxies, and security chains; never “diagnose” a 403 by disabling JWT validation. For Bearer-only APIs, **401** usually means missing or invalid token authentication; **403** usually means authenticated yet lacking a required authority.

## 9. Unit Testing the Converter with JUnit — Independent of an IdP

The most important test in this lesson checks that **specific claims** yield **the exact expected set of authorities**, without inventing extra permissions. The test below builds a mock `Jwt` object in the JVM to verify mapping logic—**it is not a signed JWT or a decoder test**.

File **`src/test/java/com/example/orders/ApiAuthoritiesConverterTest.java`**:

```java
package com.example.orders;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ApiAuthoritiesConverterTest {

    private final ApiAuthoritiesConverter converter =
        new ApiAuthoritiesConverter();

    @Test
    void combinesScopesApprovedRolesAndPermissions() {
        Jwt jwt = Jwt.withTokenValue("test-value")
            .header("alg", "RS256")
            .claim("sub", "user-42")
            .claim("scope", "orders:read orders:write")
            .claim("realm_access", Map.of(
                "roles", List.of("ADMIN", "NOT_APPROVED")))
            .claim("permissions", List.of(
                "orders:approve", "unrecognized:permission"))
            .build();

        Set<String> actual = converter.convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(Set.of(
            "SCOPE_orders:read",
            "SCOPE_orders:write",
            "ROLE_ADMIN",
            "PERM_orders:approve"
        ), actual);
    }

    @Test
    void missingCustomClaimsDoNotCreateExtraAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-value")
            .header("alg", "RS256")
            .claim("sub", "user-99")
            .claim("scp", List.of("orders:read"))
            .build();

        Set<String> actual = converter.convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertEquals(Set.of("SCOPE_orders:read"), actual);
    }
}
```

Run:

```bash
./gradlew test
```

With the exact sample code and Spring Boot 3 dependencies, both tests are **expected to PASS**. `Set` ordering is irrelevant for comparison, so the tests do not depend on the order Spring returns authorities. `Jwt.withTokenValue(...)` builds a JWT object for mapping tests; it **does not** verify signature, audience, issuer, or lifetime.

### 9.1. Testing the Filter Chain via MockMvc with a Mocked JwtDecoder

To verify HTTP endpoints receive authorities via **BearerTokenAuthenticationFilter → JwtAuthenticationConverter**, use `@SpringBootTest` and `@AutoConfigureMockMvc`, mock JwtDecoder, and send `Authorization: Bearer demo-reader`. This example fits Spring Boot 3.x where `@MockBean` is still supported (in newer versions it may emit a deprecation warning):

File **`src/test/java/com/example/orders/ApiPolicyTest.java`**:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiPolicyTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    @Test
    void bearerScopesAllowReadButNotApprove() throws Exception {
        Jwt reader = Jwt.withTokenValue("demo-reader")
            .header("alg", "RS256")
            .claim("sub", "user-42")
            .claim("scope", "orders:read")
            .build();

        when(decoder.decode("demo-reader")).thenReturn(reader);

        mvc.perform(get("/api/orders")
                .header("Authorization", "Bearer demo-reader"))
            .andExpect(status().isOk());

        mvc.perform(post("/api/orders/approve")
                .header("Authorization", "Bearer demo-reader"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/audit")
                .header("Authorization", "Bearer demo-reader"))
            .andExpect(status().isForbidden());
    }
}
```

In this test, **the decoder is mocked**, so the test shows that the policy/filter converter processes authorities as expected, rather than proving NimbusJwtDecoder's signature/issuer/audience validation. Write separate integration tests with JWTs signed by a test key or test IdP to verify `JwtDecoder` rejects tokens with wrong issuer, wrong audience, expiration, or bad signatures.

If using `SecurityMockMvcRequestPostProcessors.jwt()` directly, note that helper usually builds a pre-made `JwtAuthenticationToken` and may **bypass the custom JwtDecoder/JwtAuthenticationConverter**, so such a test alone does not prove your configured converter ran. Use converter unit tests plus HTTP integration tests with a mocked decoder as above to cover both stages separately.

## 10. Method Security, Authority Expressions, and AND/OR Rules

With `@EnableMethodSecurity`, business methods can declare:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderDto getOrder(long orderId) {
    // Verify permission to view the order and ownership/tenant in the service.
    return loadAuthorizedOrder(orderId);
}
```

This is an **illustrative method snippet**, not a standalone compilable class since `OrderDto` and `loadAuthorizedOrder` depend on the application. The full runnable example in section 8 uses controller `@PreAuthorize` and does not need those types.

If both scope and role are required:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:write') and hasRole('ADMIN')")
```

If either privilege is sufficient (must have a specific business justification):

```java
@PreAuthorize(
    "hasAuthority('PERM_orders:approve') or hasRole('ADMIN')")
```

`and` is stricter than `or`; choose according to policy, never assuming admin always overrides every scope. **An authority check never replaces checking whether the subject is authorized for a specific object.** For example, updating an order must verify `order.tenantId` matches the permitted tenant, not merely check `SCOPE_orders:write`.

When policies span many controllers/services, store authority names as constants or in a shared policy class to avoid `SCOPE_`, `ROLE_`, `PERM_` drift between mapping and checks. However, never use a single global `ADMIN` constant across all tenants when real permissions are tenant-scoped.

## 11. Decoder Claim Customization and Data Type Mapping

Spring Security may convert the types of certain JWT claims like `exp` (timestamp) and `aud` (audience list), while **custom claims** may be strings, lists, maps, or null depending on the provider. Converters must guard against:

- **Missing claims:** add no authorities; safe logging can help detect non-conforming tokens.
- **Mistyped claims:** do not coerce `"ADMIN,SUPPORT"` into a list unless specified by the contract and tested in the parser.
- **Role casing:** stick to the exact contract; avoid “promoting” an arbitrary string to `ADMIN`.
- **Nested claims:** check the type of each map; never use blind casts that could throw `ClassCastException`.
- **Multiple authority sources:** decide precedence, merging, or picking a single source. Prevent an authority from realm A from accidentally applying to realm B.
- **Multi-tenancy:** tokens must bind the tenant in a trusted claim, and policies must check permissions *within the current tenant*, not just a global role list.

If an IdP only emits roles under `resource_access.orders-api.roles`, adjust the converter to that claim. If permissions are managed only in a backend DB, do not trust roles inside a JWT as the source of truth for fast-changing permissions: use a custom `AuthorizationManager` or permission-checking service with clear caching/invalidation and auditing. Access tokens are snapshots; changing a role in the IdP does not revoke already-issued tokens until they expire or a revocation/lookup mechanism applies.

### 11.1. Example Configuring a Single Differently Named Claim

When a token uses `scp` as a standard string or list, the default already handles it. If the IdP uses a `custom_scopes` claim:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();
scopes.setAuthoritiesClaimName("custom_scopes");
scopes.setAuthorityPrefix("SCOPE_");
```

However, use this **instead of** the scope converter in section 7 if the contract changes—do not add both reading inconsistent claims without defining merge behavior. When a claim uses a special delimiter instead of spaces, configure it using the API appropriate for your Spring Security version or normalize the claim at the IdP.

## 12. Opaque Access Tokens: Same Goal, Different Customization Point

A JWT Resource Server verifies signatures/claims with `JwtDecoder`, then runs `JwtAuthenticationConverter`. Conversely, an **opaque access token** has no JWT payload for the API to read locally; the Resource Server typically calls the Authorization Server's **introspection endpoint**, receives `active` and attributes, and constructs an `Authentication`.

With opaque tokens:

- Configure `.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(...))` with a trusted introspector/credentials.
- Check `active=true` in the introspection result plus required issuer/audience/resource constraints per IdP design.
- To convert roles/permissions into GrantedAuthority instances, customize the **introspection principal/authentication converter**, rather than attaching `JwtAuthenticationConverter` to opaque tokens.
- Endpoint authorization via `hasAuthority(...)` can remain identical if both JWT and opaque branches normalize to consistent authority names.

Never attempt to Base64-decode an opaque token and treat it as a JWT. And never assign authorities from unverified client metadata instead of the introspection result.

## 13. Troubleshooting When Scopes or Permissions Do Not Work

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Valid token yet `GET /api/orders` returns 403 | `SCOPE_orders:read` missing from Authentication | Inspect `scope`/`scp` claims, prefix, audience, and policy |
| `hasRole("ADMIN")` always returns 403 | Converter didn't emit `ROLE_ADMIN`, or roles claim has wrong path/type/case | Check claim contract and actual post-converter authorities |
| Token has `roles=["ADMIN"]` yet no ROLE_ADMIN | Example converter reads `realm_access.roles`, not top-level `roles` | Update extractor to match IdP and add tests |
| Token has permission yet `hasAuthority("orders:approve")` returns 403 | Converter emits `PERM_orders:approve` | Use the matching prefix or align the policy |
| Calling `setAuthoritiesClaimName("permissions")` drops scopes | Custom converter replaced the scope converter | Combine sources using a composite converter |
| 401 on an apparently valid JWT | Bad signature/JWK, `iss`, `aud`, `exp`, or token format | Check token verification logs; never relax permissions to fix a 401 |
| Token is an ID Token instead of an access token | Client sent login token; wrong audience/semantics | Require access tokens with the right audience; reject ID Tokens |
| Admin from another client gains access | Converter reads global/multi-app roles unrestricted | Bind audience and role claim to the specific API/client |
| Logged out / role revoked yet old token still works | JWT is a snapshot and not yet expired | Use appropriate TTLs, revocation/introspection, or dynamic permission checks |
| Token with read scope can mutate data | Overly broad `anyRequest().authenticated()` or wrong matcher | Use method-specific matchers, deny-by-default, test 403 |
| User with scope reads another tenant's data | Only checked authority without checking resource/tenant | Add object-level authorization and cross-tenant tests |
| `@PreAuthorize` does not execute | Missing `@EnableMethodSecurity`, self-invocation bypassing proxy, or wrong bean | Enable method security and place guard on a Spring-proxied service |
| `.with(jwt())` test passes yet production returns 403 | Test injected authorities directly, skipping real converter | Unit test converter separately + HTTP test through mocked decoder / test IdP |
| Error occurs only on POST endpoints | May be CSRF or method policy, not necessarily scopes | Inspect credential mechanism and each SecurityFilterChain |

### 13.1. Observing Authorities Without Leaking Tokens

When debugging, **never print raw Bearer tokens, client secrets, or sensitive claims into logs**. Log at minimum non-sensitive details such as request ID, endpoint name, authentication success/failure, standardized reason code, authority names if internal policy permits, and correlation ID, with redaction and log access controls.

A demo `/api/me` endpoint helps inspect post-converter authority lists in test environments; do not use it as a substitute for service-layer data checks. To compare tokens, inspect decoded claims only in secure environments and avoid pasting real tokens onto external websites.

## 14. Resource Server Acceptance Checklist

1. **Right token type:** API accepts access tokens, never confusing them with ID Tokens or refresh tokens.
2. **Right trust boundaries:** matching signature/algorithm/JWK, issuer, lifetime, audience, plus token-type/tenant validators if needed.
3. **Right default mapping:** `scope` or `scp` converts to `SCOPE_<scope>`, and `hasAuthority` uses that exact name.
4. **Right custom claim contract:** roles/permissions are issued by the IdP for **this API**, with exact path, data types, and casing.
5. **Right custom converter:** preserves scopes when needed, whitelists roles/permissions, avoids granting rights from untrusted strings or mistyped claims.
6. **Right authorization policy:** GET read requires `SCOPE_orders:read`; approve requires `PERM_orders:approve`; admin requires `ROLE_ADMIN`; undeclared routes are denied.
7. **Right object-level policy:** tenant/owner/resource relationships are checked beyond scopes or roles.
8. **Right testing:** converter unit tests, HTTP policy integration tests, JWT validation tests with test keys/IdP; covering 401, 403, 200, and invalid claims.
9. **Right operations:** key rotation, token TTL, permission revocation, log redaction, and separating cookies/CSRF from Bearer-only APIs.

**Summary:** `scope`/`scp` in a valid JWT are converted to `SCOPE_...` by Spring Security by default. When you need additional roles and permissions from custom claims, configure `JwtAuthenticationConverter` with a combined converter, **without losing scopes**, align the `SCOPE_`, `ROLE_`, and `PERM_` prefixes, and protect the API with `hasAuthority`/`hasRole` properly. Granting authorities is only safe once the token's issuer, audience, signature, and lifetime are verified, and real permissions remain bound to the target resource/tenant.
