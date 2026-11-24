# Authority Mismatches Caused by ROLE_, SCOPE_, Claim Mapping, or Caching

> **Scope:** Diagnosing and fixing authorization errors in **Spring Security Servlet**, Spring Boot 3.x, Spring Security 6.x, Java 17+. This guide traces from HTTP 401/403 down to `Authentication.getAuthorities()`, explains `ROLE_`/`SCOPE_`, converts JWT/OIDC claims, and identifies stale permissions in `HttpSession`, access tokens, directories, or caches. **Never** fix 403 errors by disabling security.

## 1. The Problem and Symptoms

A system can exhibit very different symptoms:

- A user was just added to the `ADMIN` group in the IdP, yet `@PreAuthorize("hasRole('ADMIN')")` still returns 403.
- The token has `scope: "report.read"`, while the service checks `hasRole('report.read')`.
- `@WithMockUser(roles = "ADMIN")` makes tests PASS, yet real JWTs from the IdP are still rejected.
- A permission was revoked in the directory, yet a user with an old session can still perform the operation.
- A web page signed in via `oauth2Login()` has different authorities from an API using `oauth2ResourceServer().jwt()`.
- The `roles` claim appears missing because the IdP actually emits `realm_access.roles` or `resource_access.<client>.roles`.
- A POST request gets 403 due to **CSRF**, yet the team changes `GrantedAuthorityDefaults`.
- Two endpoints hit by the same user route to different `SecurityFilterChain`s, resulting in different authentication/authorization behavior.

An **“unauthorized / forbidden”** failure can originate across six layers:

```text
HTTP request
     |
Selected SecurityFilterChain
     |
Authentication filter -> AuthenticationManager / JwtDecoder
     |
Authentication principal + GrantedAuthority
     |
URL authorization / method security expression
     |
Business permission / resource ownership
     |
     Freshness issues: token, session, user/group cache, policy cache
```

First separate authentication failures from authorization failures:

| Outcome | Clue | Diagnostic Warning |
|---|---|---|
| 401 Unauthorized | Missing credentials; wrong JWT signature/issuer/audience/expiry; Basic/Bearer entry point | Do not immediately blame `hasRole` |
| 302 to login | Browser lacks a session and form/OIDC entry point redirects | Not the endpoint serving data |
| 403 Forbidden | Authenticated yet lacking authority, or CSRF/WAF/deny rule | Not always a prefix issue |
| 200 OK | Request passed the checked layers | Does not prove object-level authorization across all resources |

**Principle:** pinpoint the filter and rule that actually made the decision, inspect actual authorities and when permissions were issued, and only then fix the exact spot.

## 2. Distinguishing Principal, Role, Authority, Scope, and Claim

`Authentication` carries a principal and a collection of `GrantedAuthority`. With `SimpleGrantedAuthority`, each authority is a **string** matched against rules.

- **Principal:** caller identity, such as username, user ID, or `issuer + subject`. Being authenticated does not grant every permission.
- **Role:** a permission group like `ADMIN` or `REPORT_READER`, conventionally represented with the `ROLE_` prefix in Spring Security.
- **Authority:** the actual string returned by `Authentication.getAuthorities()`, such as `ROLE_ADMIN` or `SCOPE_report.read`.
- **OAuth2 scope:** the scope an access token is permitted to exercise, such as `report.read`, typically reflecting client/token capabilities toward an API.
- **Claim:** a field inside a JWT/ID token such as `groups`, `roles`, `scp`, `scope`, or `aud`. Claims are raw input data; a converter/mapper turns them into `GrantedAuthority`.
- **Business permission:** permission to act on a specific resource, such as which tenant owns a report, transaction state, or ownership. Having the right role in a different tenant must still be denied when policy requires it.

Scope flow:

```text
Access token: {"scope":"report.read report.export"}
           |
JwtGrantedAuthoritiesConverter (default)
           |
SCOPE_report.read, SCOPE_report.export
           |
@PreAuthorize("hasAuthority('SCOPE_report.read')")
           |
         Allowed
```

Custom role flow:

```text
Access token: {"app_roles":["ADMIN"]}
           |
Trusted issuer + audience validation
           |
Custom role converter (allowlist ADMIN, AUDITOR)
           |
ROLE_ADMIN
           |
@PreAuthorize("hasRole('ADMIN')")
           |
         Allowed
```

Never assume a root `roles` claim, an LDAP group, or any JSON value named `admin` automatically confers admin power. Only a trusted source authorized to grant roles for that API should map to internal authorities.

## 3. ROLE_: How Does hasRole Differ from hasAuthority?

Under the familiar **default role prefix** setup:

- `hasRole("ADMIN")` looks for authority **`ROLE_ADMIN`**.
- `hasAuthority("ROLE_ADMIN")` requires the exact string `ROLE_ADMIN`.
- `hasAuthority("ADMIN")` requires `ADMIN` **without** adding a prefix.
- `@WithMockUser(roles = "ADMIN")` creates authority `ROLE_ADMIN`.
- `@WithMockUser(authorities = "ADMIN")` creates `ADMIN`, so it does not match `hasRole("ADMIN")`.
- Prefix, letter case, dots, and underscores must all match exactly.

| Present Authorities | Rule | Outcome (Default Prefix) |
|---|---|---|
| `ROLE_ADMIN` | `hasRole('ADMIN')` | Allowed |
| `ROLE_ADMIN` | `hasAuthority('ROLE_ADMIN')` | Allowed |
| `ADMIN` | `hasRole('ADMIN')` | No match |
| `ADMIN` | `hasAuthority('ADMIN')` | Allowed |
| `SCOPE_report.read` | `hasAuthority('SCOPE_report.read')` | Allowed |
| `SCOPE_report.read` | `hasRole('report.read')` | No match |
| `ROLE_ROLE_ADMIN` | `hasRole('ADMIN')` | No match |

If the app customizes `GrantedAuthorityDefaults`, `RoleHierarchy`, or expression handlers, re-verify this table. Web security, method security, and JSR-250 APIs may read prefix configuration from different extension points depending on version; never change the prefix system-wide to patch one endpoint without regression tests.

**Double-prefix bug:**

```java
// Anti-example: role from IdP is already "ROLE_ADMIN".
String role = "ROLE_ADMIN";
String authority = "ROLE_" + role; // ROLE_ROLE_ADMIN
```

Safe approach: lock down the incoming role contract, normalize intentionally in **one** converter, and enforce an exact allowlist. Never strip `ROLE_` blindly or apply substring matching to untrusted input.

## 4. SCOPE_: JWT Resource Server Scopes Are Not Roles

With `oauth2ResourceServer().jwt()`, `JwtAuthenticationConverter` typically uses `JwtGrantedAuthoritiesConverter` reading `scope` or `scp`:

- `scope` is often a space-delimited string: `"report.read report.export"`.
- `scp` may be a list: `["report.read", "report.export"]`.
- Each scope receives `SCOPE_`: `SCOPE_report.read`.
- `report.read`, `REPORT_READ`, and `report_read` are three distinct names; there is no automatic uppercasing.
- Not every IdP uses the same claim shape. Custom converters can override defaults.

When enforcing a scope, write an explicit rule:

```java
@PreAuthorize("hasAuthority('SCOPE_report.read')")
public String viewReport() {
    return "report";
}
```

This is a method inside a Spring bean protected by `@EnableMethodSecurity`, not a standalone Java class.

When changing the claim name:

```java
JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERM_");
```

This illustrative converter reads `permissions` instead of the default `scope`/`scp`. If `SCOPE_*` is still needed, you must **merge** the results of the original scope converter and the new permission converter; otherwise an “add permissions” change can wipe out all scopes.

**Do not equate scopes with business permissions:** even if a caller holds `SCOPE_report.read`, the system must still verify that the report belongs to the right organization/tenant and the caller is permitted to view it.

## 5. Claim Mapping: Where Permissions Are Most Easily Lost or Over-Granted

Illustrative JWT payload shapes:

```json
{
  "sub": "user-123",
  "aud": ["reports-api"],
  "scope": "report.read",
  "roles": ["ADMIN"],
  "groups": ["/company/reviewers"],
  "realm_access": {"roles": ["reader"]},
  "resource_access": {
    "reports-api": {"roles": ["approver"]}
  }
}
```

This is only JSON illustrating **claim structure**, not a signed access token. Across IdPs, groups/roles may reside at the root, in nested objects, or only in userinfo/ID tokens rather than access tokens.

A mapping contract must specify:

1. **Which token type?** An access token meant for APIs, or an ID token meant for browser authentication? Never accept an ID token casually in place of a bearer access token.
2. **Issuer and signature?** `iss` is allowlisted, signature validates against trusted JWKS, and algorithms are not blindly inferred from client-supplied tokens.
3. **Audience?** `aud` must contain the protected API; never accept a validly signed token issued for another service.
4. **Claim path?** `roles`, `groups`, `realm_access.roles`, or `resource_access.reports-api.roles`?
5. **Data type?** List of strings, delimited string, nested map, or null? Wrong types must fail closed with zero privileges.
6. **Semantics and authority source?** Is that issuer actually trusted to grant `ADMIN` for this application? Arbitrary groups must never become admin.
7. **Namespace and tenant?** Identical group names across two tenants or issuers do not automatically mean the same privilege.
8. **Freshness:** was the token minted before or after the group/permission changed?

**Unsafe anti-example:**

```java
// If the string contains "not-admin", contains("admin") also returns true.
String rawRole = jwt.getClaimAsString("roles");
if (rawRole != null && rawRole.contains("admin")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

This is strictly an anti-example. Real mappers must check types and match **exact names** against an allowlist after token verification.

### 5.1. OIDC Login and Resource Server Usually Do Not Share a Converter

`oauth2Login()` creates browser-login authentication, such as `OAuth2AuthenticationToken` with an `OidcUser` and a session. `oauth2ResourceServer().jwt()` creates `JwtAuthenticationToken` from a bearer access token. These two paths use distinct extension points; configuring `JwtAuthenticationConverter` on the JWT resource server does not make it apply to `OidcUser` authorities.

Meanwhile, `@WithMockUser` in unit tests constructs a synthetic context and normally **skips converters altogether**. Always ask “where did this `Authentication` come from?” before comparing authorities.

## 6. Evidence-Based Investigation Workflow for HTTP 403

### Step 1: Locate the Exact Source of 403

Check HTTP method, context path, proxy/gateway, and exception handlers. Browser-session `POST`/`PUT`/`DELETE` requests can be rejected by the CSRF filter before the controller, even with an exact admin role. A WAF 403 is also unrelated to `JwtGrantedAuthoritiesConverter`. For unauthenticated requests, 401/302 is the entry point, not necessarily an authorization failure.

### Step 2: Confirm the Right SecurityFilterChain

`securityMatcher(...)` and `@Order` pick the active chain; `requestMatchers(...)` enforces policies inside that chain. `/api/**` may use bearer JWTs while `/web/**` uses OIDC sessions and the fallback uses `denyAll`. Reverse-proxy path rewrites can cause the app to see a different URL than the browser, hitting a different chain.

### Step 3: Inspect Actual Authentication and Authorities

In tests or authorized staging environments, inspect the authentication class and authority names. **Never log raw JWTs, `Authorization` headers, tokens, credentials, or full claim sets**.

Illustrative snippet in a test:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
if (authentication != null) {
    String type = authentication.getClass().getSimpleName();
    List<String> authorityNames =
        authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted().toList();
    // Internal test assertion on type and authorityNames.
    // Never output principal PII, passwords, or bearer tokens.
}
```

Requires imports for `Authentication`, `GrantedAuthority`, `SecurityContextHolder`, and `List`. This must never become a public debug endpoint.

### Step 4: Compare Against the Active Rule

If the context holds `SCOPE_report.read` and `ROLE_REVIEWER` while the rule checks `hasRole('REPORT_READ')`, the rule is looking for `ROLE_REPORT_READ`. Clarify whether business intent is scope, role, or permission, then fix **one place**—either the expression or the converter—per the official contract.

### Step 5: Check Permission Age / Freshness

Compare token `iat`/`exp`, `HttpSession` creation time, last login time, cache TTLs, directory/IdP group sync, and when the permission changed. Self-contained JWTs **do not mutate their claims after signing**. Likewise, a `SecurityContext` persisted in a session can hold authorities from an earlier sign-in.

### Step 6: Write Both Allow and Deny Tests

Authorized users must succeed; users lacking permission, in another tenant, or carrying forged, malformed, or stale claims must be denied per policy. Fixing only the admin 200 test while omitting low-privilege tests easily introduces privilege escalation.

## 7. Caching: There Is No Single “Roles Cache”

| State Location | What Goes Stale | How to Inspect |
|---|---|---|
| Self-contained JWT | `scope`/`roles`/`groups` claims from issuance | Token `iat`/`exp`, T1/T2, TTL, revocation |
| `HttpSession`/`SecurityContextRepository` | `Authentication` from login time | Re-auth, logout, session invalidation |
| `UserDetailsService`/`UserCache` (if enabled) | User details and authorities | Cache key, TTL, eviction, account status |
| Backend `@Cacheable`/Redis | Group→permissions, tenant policy | Cache key namespace, TTL, and invalidation |
| Directory/IdP sync | Membership not yet propagated to issuer | Sync schedule, source of truth, claim issuance |
| Gateway policy cache | Stale access decisions | Keyed by account, resource, operation, tenant |
| JWKS cache | Public keys for verifying JWT signatures | Key rotation/`kid` — **not** a role cache |

**JWKS cache is not an authorization cache.** Refreshing JWKS fixes signature/key-rotation errors; it **never gives new roles to an existing token carrying old claims**.

### 7.1. Permission Was Just Granted Yet Does Not Appear

Check whether the user was added to the right group, whether the issuer minted **token T2** with the new claims, whether the converter reads the right claim, whether the session re-authenticated or reloaded context, and whether backend/IdP sync caches hold stale snapshots. Token T1 signed before the change normally keeps its old claims until expiration.

### 7.2. Permission Was Revoked Yet Still Works

This is usually the higher risk. A still-valid token T2 can retain `ROLE_ADMIN` even after the directory removed the group. Depending on SLA, use short token TTLs, introspection/revocation, server-side policy lookups, or session/token invalidation. Logging out of a browser invalidates only the relevant session, not automatically bearer tokens on other devices.

### 7.3. User A's Permissions Appear for User B

This can happen when a cache key omits issuer/subject/tenant/resource, or when security context handling in a thread pool leaks. Never treat “clear the cache” as a complete fix. Inspect `SecurityContextHolder` propagation and cleanup, cache isolation, tenant namespaces, and multi-node invalidation events.

**Cache keys** should include `issuer + stable subject + tenant + resource + action + policy version` whenever those dimensions affect outcomes. Avoid keys containing only username or role name. Size TTLs and revocation to sensitivity, measuring grant and revocation propagation latency separately.

## 8. Java 17 + Spring Boot 3.3.5 Example: Distinguishing ROLE_ and SCOPE_

Servlet API demo with two independent permissions:

- `scope`/`scp` from JWT → `SCOPE_*` via `JwtGrantedAuthoritiesConverter`.
- `app_roles` from JWT → `ROLE_*` after issuer/audience validation and allowlist filtering.
- `GET /api/reports` requires `SCOPE_report.read`.
- `GET /api/admin` requires `ROLE_ADMIN`.

**Environment limitation:** `.invalid` in config is a non-functional educational domain; the server cannot validate real bearer JWTs until pointed at a trusted issuer/JWKS. Tests use `@MockBean JwtDecoder` to exercise converter/authorization logic, **not** signature checks. To test signatures, use signed test tokens and a test JWKS without mocking the decoder.

### 8.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') { useJUnitPlatform() }
```

File tree:

```text
src/main/java/demo/authority/
  AuthorityApplication.java
  SecurityConfig.java
  ReportService.java
  ApiController.java
src/main/resources/application.yml
src/test/java/demo/authority/
  AuthorityIntegrationTest.java
  MethodRulesTest.java
```

### 8.2. application.yml and Main Application

`src/main/resources/application.yml`:

```yaml
app:
  security:
    issuer: "https://id.example.invalid/"
    audience: "reports-api"
    jwk-set-uri: "https://id.example.invalid/jwks.json"
```

`src/main/java/demo/authority/AuthorityApplication.java`:

```java
package demo.authority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityApplication.class, args);
    }
}
```

### 8.3. SecurityConfig: Audience Validation + Two-Namespace Mapper

`src/main/java/demo/authority/SecurityConfig.java`:

```java
package demo.authority;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    OAuth2TokenValidator<Jwt> jwtValidator(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {
        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Required audience missing", null));

        return new DelegatingOAuth2TokenValidator<>(
            standard, audienceCheck);
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwk-set-uri}") String jwksUri,
            OAuth2TokenValidator<Jwt> validator) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
        decoder.setJwtValidator(validator);
        return decoder;
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();
        Set<String> allowed = Set.of("ADMIN", "AUDITOR");

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();

            Collection<GrantedAuthority> scopes =
                scopeConverter.convert(jwt);
            if (scopes != null) {
                authorities.addAll(scopes);
            }

            Object claim = jwt.getClaim("app_roles");
            if (claim instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if (item instanceof String role &&
                            allowed.contains(role)) {
                        authorities.add(new SimpleGrantedAuthority(
                            "ROLE_" + role));
                    }
                }
            }
            return authorities;
        };

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        converter.setPrincipalClaimName("sub");
        return converter;
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http, JwtAuthenticationConverter converter)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
            .build();
    }
}
```

Explanation:

- `NimbusJwtDecoder` fetches public signing keys from **configured trusted JWKS**; the validator checks issuer/standard claims and **audience `reports-api`**. Never pick a key URL from the token's `jku` header.
- `JwtGrantedAuthoritiesConverter` keeps scopes as `SCOPE_*`; the custom mapper adds `ROLE_*` only when `app_roles` is a `Collection` and its values appear in the allowlist.
- `app_roles` is an **assumed contract** between the API and a trusted issuer; the code's allowlist does not replace IdP governance over who receives `ADMIN`.
- If a claim already arrives as `ROLE_ADMIN`, the code **will not map** it into `ROLE_ROLE_ADMIN` because that value is not in the allowlist.
- Both endpoints require authentication; method security enforces specific permissions. There is no `permitAll` on `/api/**`.

### 8.4. Service and Controller

`src/main/java/demo/authority/ReportService.java`:

```java
package demo.authority;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('SCOPE_report.read')")
    public String read() {
        return "report";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String admin() {
        return "admin";
    }
}
```

`src/main/java/demo/authority/ApiController.java`:

```java
package demo.authority;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    private final ReportService service;

    public ApiController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/api/reports")
    public String reports() {
        return service.read();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return service.admin();
    }
}
```

The role endpoint does not automatically grant the scope, and the scope endpoint does not automatically grant the role. In production, per-report-ID and per-tenant authorization is an additional check.

## 9. MockMvc Testing of Mapper and Method Security

### 9.1. HTTP Bearer Tests with a Mocked Decoder

`src/test/java/demo/authority/AuthorityIntegrationTest.java`:

```java
package demo.authority;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorityIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired JwtAuthenticationConverter converter;
    @Autowired OAuth2TokenValidator<Jwt> validator;

    @MockBean JwtDecoder decoder; // Tests converter/filter only, not signature.

    private Jwt token(String value, String scope,
                      List<String> roles, String issuer,
                      List<String> audience) {
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .claim("iss", issuer)
            .claim("sub", "test-user")
            .claim("aud", audience)
            .claim("scope", scope)
            .claim("app_roles", roles)
            .issuedAt(Instant.now().minusSeconds(60))
            .expiresAt(Instant.now().plusSeconds(600))
            .build();
    }

    @BeforeEach
    void setUp() {
        String issuer = "https://id.example.invalid/";
        List<String> aud = List.of("reports-api");
        when(decoder.decode("read")).thenReturn(
            token("read", "report.read", List.of(), issuer, aud));
        when(decoder.decode("admin")).thenReturn(
            token("admin", "", List.of("ADMIN"), issuer, aud));
        when(decoder.decode("both")).thenReturn(
            token("both", "report.read", List.of("ADMIN"), issuer, aud));
        when(decoder.decode("unknown-role")).thenReturn(
            token("unknown-role", "", List.of("SUPER_ADMIN"),
                  issuer, aud));
    }

    @Test
    void scopeCanReadButCannotAdmin() throws Exception {
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer read"))
            .andExpect(status().isOk())
            .andExpect(content().string("report"));
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer read"))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleCanAdminButNotReadWithoutScope() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer admin"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    void combinedClaimsWork() throws Exception {
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer both"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer both"))
            .andExpect(status().isOk());
    }

    @Test
    void unapprovedRoleDoesNotGrantAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer unknown-role"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousIs401() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void converterUsesBothPrefixes() {
        Jwt jwt = token("inspect", "report.read", List.of("ADMIN"),
            "https://id.example.invalid/", List.of("reports-api"));
        var names = converter.convert(jwt).getAuthorities().stream()
            .map(a -> a.getAuthority()).toList();
        assertTrue(names.contains("SCOPE_report.read"));
        assertTrue(names.contains("ROLE_ADMIN"));
        assertFalse(names.contains("ROLE_ROLE_ADMIN"));
    }

    @Test
    void issuerAndAudienceValidatorRejectsWrongClaims() {
        Jwt good = token("good", "report.read", List.of(),
            "https://id.example.invalid/", List.of("reports-api"));
        Jwt otherAudience = token("bad-aud", "report.read", List.of(),
            "https://id.example.invalid/", List.of("other-api"));
        Jwt otherIssuer = token("bad-iss", "report.read", List.of(),
            "https://other.example.invalid/", List.of("reports-api"));
        assertFalse(validator.validate(good).hasErrors());
        assertTrue(validator.validate(otherAudience).hasErrors());
        assertTrue(validator.validate(otherIssuer).hasErrors());
    }
}
```

**Scope:** `@MockBean JwtDecoder` replaces the decoder, so HTTP tests **do not verify JWT signatures or trusted JWKS**. The validator test invokes issuer/audience rules directly, also without signature verification. For real verification, use tokens signed by test keys against a test JWKS/IdP **without mocking the decoder**, testing invalid signatures, wrong `iss`/`aud`, and expired/`nbf` tokens.

### 9.2. Method Tests: Do Not Confuse Mock Users with JWT Converters

`src/test/java/demo/authority/MethodRulesTest.java`:

```java
package demo.authority;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MethodRulesTest {
    @Autowired ReportService service;

    @Test
    @WithMockUser(roles = "ADMIN")
    void defaultRolePrefixWorks() {
        assertEquals("admin", service.admin());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void bareAuthorityIsNotAdminRole() {
        assertThrows(AccessDeniedException.class, service::admin);
    }

    @Test
    @WithMockUser(authorities = "SCOPE_report.read")
    void exactScopeIsAccepted() {
        assertEquals("report", service.read());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotAutomaticallyHaveScope() {
        assertThrows(AccessDeniedException.class, service::read);
    }
}
```

Run with Gradle Wrapper and Java 17:

```bash
./gradlew test
./gradlew test --tests demo.authority.AuthorityIntegrationTest
./gradlew test --tests demo.authority.MethodRulesTest
```

A test expecting 401/403 or `AccessDeniedException` **PASSES when the rejection works properly**. There is no fixed verbatim Gradle stdout due to version and caching differences.

## 10. Real JWT Verification and Permission Freshness

### 10.1. Separating Decoder Tests from Converter Tests

When using a test IdP or a test JWKS server, mint access tokens signed by a test private key and **do not mock `JwtDecoder`**. Matrix:

| Scenario | Expectation |
|---|---|
| Valid signature/issuer/audience and required scope/role | 200 |
| Invalid signature | 401 |
| Disallowed `alg` | 401 |
| Unknown issuer or different API audience | 401 |
| Expired token / `nbf` outside valid window | 401 |
| Valid token lacking required authority | 403 |
| Unexpected/wrong-type role claim | Must not grant admin |
| Valid-privilege token accessing another tenant's object | 403 per resource policy |

Use only **test keys/test users**; never place production JWTs or private keys into CI or logs.

### 10.2. Rehearsing Permission Changes

1. Sign in a test user with low privilege; record timestamps of token **T1**/session **S1** and API results; never log raw tokens.
2. Add the role in the IdP/directory. Observe that T1/S1 may continue using old permissions.
3. Mint token **T2** or sign in again for S2. Inspect new claims and the authority converter.
4. Revoke the role. Check whether T2/S2 retains stale permission snapshots; compare against your **revocation SLA**.
5. Enforce token expiry/introspection/revocation, session invalidation, or policy lookups as required; test across all nodes and devices.
6. Repeat with warm/cold caches, group syncs, and two tenants to detect cache-key mismatches.

**T1 is immutable once signed**; refreshing JWKS does not change roles inside T1. Logging out of a browser session also does not automatically revoke access tokens held on another device.

## 11. Common Mistakes and Fixes

**1. `hasRole('report.read')` for a JWT scope.** Looks for `ROLE_report.read`, whereas the token yields `SCOPE_report.read`. Fix to match scope semantics.

**2. `@WithMockUser(roles='ADMIN')` passes, so the JWT converter is assumed right.** Wrong: the annotation creates `ROLE_ADMIN` directly without running the converter.

**3. Getting `ROLE_ROLE_ADMIN`.** The converter added a prefix when the claim already carried one. Normalize input and allowlist in one place.

**4. Losing scopes after changing `authoritiesClaimName`.** The new converter only reads the custom claim. Merge scopes and custom permissions.

**5. Nested claim read as root.** Verify the issuer contract, claim path, and type; never fall back to admin.

**6. Trusting roles from a validly signed token with the wrong audience.** Add an audience validator and API trust policy.

**7. Assigning roles by substring match.** `not-admin` matches `admin`; use an exact allowlist.

**8. Using `JwtAuthenticationConverter` for OIDC browser logins without an equivalent mapper.** The two authentication flows are separate.

**9. 403 is CSRF yet `ROLE_` is changed.** Test POST with valid CSRF to tell them apart.

**10. Opening `permitAll` to avoid 403.** Creates a vulnerability; fix the mapper, rule, or permission source, always keeping negative tests.

**11. JWT retains stale claims.** Self-contained tokens do not auto-refresh; enforce short TTLs, revocation, or policy lookups.

**12. `HttpSession` holds a stale `SecurityContext`.** Check re-authentication, session expiration, and invalidation when permissions change.

**13. Confusing JWKS cache with permission cache.** Public-key caching affects signatures, not claims.

**14. Cache missing issuer/tenant/resource keys.** Can cause another user to inherit the wrong permission decision.

**15. Method rules bypassed due to missing `@EnableMethodSecurity` or instantiating with `new`.** Inject the Spring bean proxy and add deny tests.

**16. Changing role prefix app-wide without auditing rules.** Requires migration and tests across web/method/JSR-250 per version.

## 12. Diagnostic Checklist and Conclusion

- [ ] Verify whether 401/302/403 came from the gateway, CSRF, filter, or method rule.
- [ ] Identify the active `SecurityFilterChain` and `Authentication` class.
- [ ] Compare actual authorities against the rule (prefix, case, scope/role namespace).
- [ ] Verify JWT signature, issuer, audience, expiry, and token type **before** trusting claims.
- [ ] Verify claim path, type, semantics, and allowlist turning `roles`/`groups` into authorities.
- [ ] Confirm the converter is wired into the right authentication flow (JWT API vs. OIDC browser).
- [ ] Compare token/session timestamps against when groups/permissions changed.
- [ ] Inspect `HttpSession`/`SecurityContextRepository`, user caches, IdP sync, and Redis/gateway policy caches; do not confuse with JWKS cache.
- [ ] Ensure cache keys distinguish issuer, subject, tenant, and resource/action where relevant.
- [ ] Test authorized and unauthorized users, wrong issuer/aud, malformed roles, stale vs. fresh tokens, and cross-tenant access.
- [ ] Define and measure revocation SLAs, especially for ADMIN/financial operations.
- [ ] Maintain deny-by-default; never disable CSRF or remove `@PreAuthorize` to “fix” 403.

**Conclusion:** Accurate access control requires **a trusted identity source → a converter producing exact `ROLE_`/`SCOPE_` authorities → rules checking the right authority → tokens/sessions/caches keeping permissions fresh enough**. An HTTP 403 is not an invitation to weaken rules; inspect evidence at every layer, fix the root cause, and prove unauthorized users remain denied.