# 29.8. Testing Authority Mapping and URL or Method Authorization

> **Module:** Spring Security OAuth 2.0 OIDC Client  
> **Chapter:** 29. Servlet Testing  
> **Focus:** Testing the steps that convert OAuth2/OIDC Login data into `GrantedAuthority` instances and enforce those authorities at Spring Security Servlet's two protection layers: URL rules in `SecurityFilterChain` and method rules such as `@PreAuthorize`. Clearly separate mapping tests, HTTP tests, and service-proxy tests to avoid "green" tests where the real app still grants permissions incorrectly.

An OIDC application can log users in successfully yet still handle **authorization** wrong. For example, the Identity Provider (OP) returns the claim `groups=["finance-viewers"]`. The application must map that group to `PERM_REPORT_READ`, not `ROLE_ADMIN`. Afterward, `GET /api/reports/42` is permitted, whereas `POST /api/reports/new` and `GET /api/admin/audit` must be denied. If a service method that exports reports requires `PERM_REPORT_EXPORT`, the endpoint must not bypass this requirement just because the URL permitted reading reports.

There are three easy places to make mistakes:

1. **Wrong authority mapping**: mixing `groups`, `scope`, roles, and business permissions; granting `ROLE_ADMIN` from a claim without checking context.
2. **Wrong URL rules**: missing matchers, overly broad matcher ordering, confusing `hasRole` with `hasAuthority`, or a POST test rejected by CSRF making you think authorization worked.
3. **Method authorization bypassed**: forgetting `@EnableMethodSecurity`, calling internal methods without going through the proxy, or tests calling an object created with `new` so the real interceptor is never tested.

Spring Security Test supports `MockMvc`, `oidcLogin()`, `oauth2Login()`, `@WithMockUser`, and several mechanisms for attaching `Authentication` to requests/test contexts. Remember: **simulating `Authentication` differs from verifying the full OIDC Login flow**. A test using `oidcLogin().authorities(...)` verifies how authorization handles the supplied authorities; it does not itself prove the production-configured mapper translates claims properly.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish authentication, authorization, OIDC identity claims, OAuth2 scopes, roles, and business permissions.
2. Understand how `OAuth2AuthenticationToken`, `OidcUser`, `OidcUserAuthority`, and `GrantedAuthority` relate.
3. Distinguish `ROLE_ADMIN`, `SCOPE_reports.read`, and `PERM_REPORT_READ` in Spring Security.
4. Design a mapper from verified OIDC groups to authorities using an allowlist.
5. Write unit tests for `GrantedAuthoritiesMapper` without a real OP.
6. Use `oidcLogin()` and `oauth2Login()` in `MockMvc` to test URL policies.
7. Understand that `oidcLogin()` does not automatically run `OidcUserService`, `GrantedAuthoritiesMapper`, or ID Token verification via an OP.
8. Test anonymous requests, authenticated users lacking permissions, and authorized users.
9. Test `requestMatchers(HttpMethod, pattern)` rules and catch differences between GET, POST, PUT, and DELETE.
10. Distinguish HTTP 403 due to CSRF from 403 due to missing `GrantedAuthority`.
11. Test `@PreAuthorize` through a Spring-managed service proxy with `@EnableMethodSecurity`.
12. Spot self-invocation, proxy bypasses, and tests that omit method security configuration.
13. Test the intersection of URL authorization and method authorization.
14. Test authority isolation across multiple registrations, issuers, and tenants.
15. Build a positive/negative matrix covering missing claims, mixed case, scope mismatches, and revoked permissions.
16. Know when a real Authorization Code/OIDC Login integration test with a mock OP is needed instead of just mocking `Authentication`.

## 2. Map of Testing Layers

| Layer | Input | What must be proven | Appropriate tool |
|---|---|---|---|
| Claim interpretation | Verified ID Token or UserInfo claims | Provider claims/groups interpreted properly | Claim-policy unit test, mock OP |
| Authority mapping | `OidcUserAuthority` and input authorities | `GrantedAuthority` list matches allowlist | `GrantedAuthoritiesMapper` unit test |
| OAuth2 Login wiring | Login result from OP and security configuration | Real mapper/service invoked in login pipeline | Mock OP/AS integration test |
| URL authorization | Authentication with authorities | Request allowed/denied by HTTP method and path | `MockMvc` + `oidcLogin()` |
| Method authorization | `SecurityContext` when calling a Spring bean | `@PreAuthorize` enforced via proxy | `@SpringBootTest`, `@WithMockUser`, or test authentication |
| Business tenancy | Principal + tenant/resource owner | No cross-tenant resource access even with matching roles | Service/controller integration tests |
| End-to-end behavior | Browser, authorization code, callback, tokens | Routing, validation, mapping, and policy wired together | Test OP + app + fake Resource Server |

**Never use a single test to stand in for every row.** Each layer has its own contract; a reliable test suite covers the full path from claims to API decisions.

## 3. Authentication Is Not Authorization

**Authentication** answers "who has been authenticated?". With OIDC Login, Spring Security verifies data from the OP and creates an appropriate `Authentication`.

**Authorization** answers "what is this principal allowed to do with which resource?". It may rely on:

- `GrantedAuthority` instances inside `Authentication`;
- role hierarchy;
- annotations such as `@PreAuthorize`;
- ownership/tenant membership;
- resource attributes;
- a policy database or authorization service.

Example of an OIDC user with subject `employee-734` who authenticated validly, yet holds read-only access:

```text
OIDC identity:
  issuer = https://login.corporate.test/realm
  sub = employee-734
  groups = ["reports-readers"]

Application authorities:
  PERM_REPORT_READ

Allowed:
  GET /api/reports/42

Denied:
  POST /api/reports/new
  GET /api/admin/audit
  GET /api/reports/42/export  (if PERM_REPORT_EXPORT is also required)
```

Never grant access merely because "login succeeded" or "the ID Token has a valid signature" while skipping claim mapping and business authorization checks.

## 4. Common Authorities in Spring Security

`GrantedAuthority` represents a permission as a string or a concrete implementation. `SimpleGrantedAuthority` is the most common implementation.

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority admin =
    new SimpleGrantedAuthority("ROLE_ADMIN");

GrantedAuthority readReports =
    new SimpleGrantedAuthority("PERM_REPORT_READ");

GrantedAuthority oauthScope =
    new SimpleGrantedAuthority("SCOPE_reports.read");
```

Distinctions:

| Authority string | How it is checked | Illustrative meaning |
|---|---|---|
| `ROLE_ADMIN` | `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` | Application role |
| `ROLE_USER` | `hasRole("USER")` | Application role |
| `PERM_REPORT_READ` | `hasAuthority("PERM_REPORT_READ")` | Business permission |
| `PERM_REPORT_EXPORT` | `hasAuthority("PERM_REPORT_EXPORT")` | Data export permission |
| `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | Scope using Spring Security's prefix convention |
| `OIDC_USER` | Present only if the app explicitly constructs this string | Not a mandatory default authority |

### 4.1. `hasRole` and `hasAuthority` Differ

In common default configurations:

```java
hasRole("ADMIN")
```

checks the authority `ROLE_ADMIN`, whereas:

```java
hasAuthority("ADMIN")
```

checks the exact string `ADMIN`.

Therefore, a user holding `SimpleGrantedAuthority("ADMIN")` **does not satisfy** `hasRole("ADMIN")` under the default role prefix. If the application customizes the default role prefix, tests must reflect the real configuration.

### 4.2. Scopes Are Not Automatically Roles

An OAuth2 scope `reports.read` is turned into `SCOPE_reports.read` by many Spring Security flows. However, `hasRole("REPORTS_READ")` checks a different string; never equate scopes with roles.

With **OAuth2 Client/OIDC Login**, which authorities a scope produces depends on the configured user service and mapper. Do not infer OIDC Login behavior from a Resource Server JWT converter.

## 5. OIDC Login and Sources of Authorities

During OIDC login, Spring Security can build an `OidcUser` and authorities containing an `OidcUserAuthority`, along with scope authorities depending on implementation/configuration.

`OidcUserAuthority` carries OIDC ID Token and UserInfo data so the application can map those claims into internal permissions.

```text
OP ID Token / UserInfo
        |
        v
OIDC validation + OidcUserService
        |
        v
OidcUserAuthority / scope authorities
        |
        v
GrantedAuthoritiesMapper or custom OidcUserService
        |
        v
OAuth2AuthenticationToken.authorities
        |
        +--> URL AuthorizationManager
        |
        +--> @PreAuthorize / method security
```

**Important point:** claims from the OP are identity inputs and potentially approved permission-mapping inputs. However, belonging to an `admins` group at an OP does not automatically make a user `ROLE_ADMIN` across every tenant in the application.

## 6. Deciding Trusted Authority Sources

Before writing a mapper, determine:

1. Does the `groups` claim come from the ID Token or UserInfo?
2. Which issuers are permitted to assert that claim?
3. Is the claim a list, string, or nested JSON per the OP contract?
4. Which groups are allowed to map to which internal authorities?
5. Does the same group name across two issuers mean the same thing?
6. Must tenant membership also be verified against a database?
7. Which permissions belong to the application versus the Resource Server?
8. When a group is revoked, how are authorities stored in active sessions refreshed?

Example policy for one OP:

| Verified group claim | Application authority | Allows |
|---|---|---|
| `acme-reports-readers` | `PERM_REPORT_READ` | Reading Acme reports |
| `acme-reports-writers` | `PERM_REPORT_WRITE` | Creating/editing Acme reports per policy |
| `acme-report-exporters` | `PERM_REPORT_EXPORT` | Exporting Acme reports |
| `acme-portal-admins` | `ROLE_ADMIN` | Acme admin actions per policy |
| Group not in allowlist | No new authority granted | Fail closed |

A rule like "any group containing `admin` gets `ROLE_ADMIN`" is dangerous; group strings must be mapped strictly per verified contract, issuer, and tenant scope.

## 7. Building an Allowlist-Based `GrantedAuthoritiesMapper`

Java example using `groups` from a trusted issuer's ID Token:

```java
package example.security;

import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

public final class AcmeAuthoritiesMapper
        implements GrantedAuthoritiesMapper {

    private static final String TRUSTED_ISSUER =
        "https://login.acme.test/realms/employees";

    private static final Map<String, String> GROUP_TO_AUTHORITY =
        Map.of(
            "acme-reports-readers", "PERM_REPORT_READ",
            "acme-reports-writers", "PERM_REPORT_WRITE",
            "acme-report-exporters", "PERM_REPORT_EXPORT",
            "acme-portal-admins", "ROLE_ADMIN"
        );

    @Override
    public Collection<? extends GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> input) {

        Set<GrantedAuthority> mapped = new HashSet<>();

        for (GrantedAuthority authority : input) {
            if (authority instanceof OidcUserAuthority oidc) {
                String issuer = oidc.getIdToken()
                    .getIssuer().toString();

                if (!TRUSTED_ISSUER.equals(issuer)) {
                    continue;
                }

                List<String> groups = oidc.getIdToken()
                    .getClaimAsStringList("groups");

                if (groups == null) {
                    continue;
                }

                for (String group : groups) {
                    String appAuthority =
                        GROUP_TO_AUTHORITY.get(group);

                    if (appAuthority != null) {
                        mapped.add(
                            new SimpleGrantedAuthority(appAuthority)
                        );
                    }
                }
            }

            // Example preserves only scope authorities created
            // by the framework/provider; never promotes scopes to roles.
            String value = authority.getAuthority();

            if (value != null && value.startsWith("SCOPE_")) {
                mapped.add(authority);
            }
        }

        return mapped;
    }
}
```

### 7.1. Intentional Limits of This Example

- Maps groups solely from the ID Token per one OP's contract.
- Never reads claims from arbitrary URLs or user input.
- Grants nothing for unknown groups.
- Never turns `SCOPE_*` into `ROLE_ADMIN`.
- Never assumes a group for another tenant carries the same meaning.
- In multi-tenant/multi-registration applications, mapping must incorporate registration/issuer + tenant membership; a mapper checking issuer alone may be insufficient.
- If `groups` actually lives in UserInfo, adapt the example to the approved claim source rather than assuming the ID Token always contains `groups`.

### 7.2. Why Might This Mapper Be Insufficient for Multi-Tenancy?

`GrantedAuthoritiesMapper` receives only a collection of authorities and has no `clientRegistrationId` parameter in its method signature. When policy depends on registration/tenant, a custom `OidcUserService` using `OidcUserRequest.getClientRegistration()` paired with a membership service may fit better. Never infer tenant solely from email domains or group names.

## 8. Wiring the Mapper into OAuth2 Login

Spring Security Servlet example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class LoginAuthoritiesConfiguration {

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return new AcmeAuthoritiesMapper();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            GrantedAuthoritiesMapper mapper)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo ->
                    userInfo.userAuthoritiesMapper(mapper)
                )
            )
            .build();
    }
}
```

This snippet illustrates wiring the mapper, not the application's complete URL rules. In later sections, we replace `authorizeHttpRequests` with the full policy.

**Very important testing step:** Spring Security Test's `oidcLogin()` builds a simulated `Authentication` directly. Passing a test with `ROLE_ADMIN` in MockMvc does not mean the `userAuthoritiesMapper()` bean above ever executed.

## 9. When to Use a Custom `OidcUserService`?

`userAuthoritiesMapper` is convenient for transforming authorities after the user has been loaded. However, if you need to:

- Read extra membership data from an internal service,
- Combine registration ID, issuer, and tenant together,
- Rely on UserInfo/ID Token data per provider policy,
- Reject login if the user is suspended or lacks tenant membership, or
- Map multi-issuer/multi-tenant claims with explicit context,

then a custom `OidcUserService` or a service invoked inside `userInfoEndpoint` may fit better.

Conceptual example:

```java
OidcUserService delegate = new OidcUserService();

return request -> {
    OidcUser user = delegate.loadUser(request);
    String registrationId =
        request.getClientRegistration().getRegistrationId();

    // Verify issuer/sub and membership per registration
    // before building authorities or allowing login.
    return applyTrustedTenantPolicy(user, registrationId);
};
```

`applyTrustedTenantPolicy` is an **application-defined function**, not a Spring Security API. Tests must inject/mock the membership service and cover denied cases as well. If the custom user service constructs a `DefaultOidcUser`, preserve ID Token, UserInfo, and the name attribute per the application's contract.

## 10. Testing Dependencies

Example Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

With Maven, add `spring-security-test` with `test` scope and the Spring Boot test starter.

The examples below follow Spring Boot 3.x/Spring Security 6.x Servlet/Jakarta style. APIs/configuration may differ on other versions. Your test application context must include a `SecurityFilterChain` and the relevant controller/service beans.

## 11. Thinking in Three Test Groups Instead of One "Admin Succeeds" Test

A single test:

```java
mockMvc.perform(get("/api/admin/audit")
    .with(oidcLogin().authorities(
        new SimpleGrantedAuthority("ROLE_ADMIN")
    )))
    .andExpect(status().isOk());
```

proves only: **when `Authentication` has `ROLE_ADMIN`, the endpoint returns 200** in that test context.

It **does not prove**:

- Regular users are denied.
- `ROLE_ADMIN` is actually mapped from OIDC claims.
- The session token was verified via OIDC.
- A role from tenant A has no effect in tenant B.
- Method authorization executed.
- A request without CSRF cannot write data.
- The API is not exposed by a broader matcher.

Therefore, each rule needs at least three cases: **anonymous**, **authenticated without permission**, and **authenticated with permission**; add edge cases per risk level.

## 12. Designing the Endpoint/Authority Matrix for the Lab

Suppose the product defines:

| Method | URL | URL authorization | Additional method authorization |
|---|---|---|---|
| GET | `/api/reports/{id}` | `PERM_REPORT_READ` | Business ownership if needed |
| POST | `/api/reports/new` | `PERM_REPORT_WRITE` | Business validation |
| GET | `/api/reports/{id}/export` | `PERM_REPORT_READ` | `PERM_REPORT_EXPORT` |
| GET | `/api/admin/audit` | `ROLE_ADMIN` | Audit domain policy |
| GET | `/public/status` | Public | None |
| GET | `/api/profile` | Authenticated | None |

This is the **illustrative application's** contract, not a Spring Security default.

### 12.1. Why Does the Export URL Require Both READ and EXPORT?

A user holding `PERM_REPORT_EXPORT` without permission to read reports should not be able to export their contents. We configure `GET` reports to require `READ` and the export method to require `EXPORT`. With both layers active, the user needs **both authorities**.

If a rule existed only on the controller while the service could be invoked from a scheduler, GraphQL, or another endpoint, treat method security as an essential extra defense layer.

## 13. `SecurityFilterChain` with Explicit URL Rules

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApplicationSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/public/status", "/error"
                ).permitAll()

                .requestMatchers(
                    "/api/admin/**"
                ).hasRole("ADMIN")

                .requestMatchers(
                    HttpMethod.POST, "/api/reports/**"
                ).hasAuthority("PERM_REPORT_WRITE")

                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**"
                ).hasAuthority("PERM_REPORT_READ")

                .anyRequest().authenticated()
            )
            .oauth2Login(login -> {})
            .build();
    }
}
```

In production, `oauth2Login(login -> {})` is replaced with appropriate mapper/registration/logout/error-handling configuration. This snippet highlights defining URL rules; combine it with the mapper in section 8 when running the same test application.

### 13.1. Specific Matchers Before Broad Matchers

If you write:

```java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

the broad matcher earlier in the list handles `/api/admin/**` first, making the subsequent role check ineffective for those requests.

In the `authorizeHttpRequests` DSL, matcher order matters: **place more specific rules before broader rules** and add negative tests for sensitive endpoints.

### 13.2. GET Differs from POST

The two matchers:

```java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
.requestMatchers(HttpMethod.POST, "/api/reports/**")
```

are not equivalent. In tests, pass the matching HTTP method and include a CSRF token for state-changing requests when CSRF protection is active.

### 13.3. `anyRequest().authenticated()` vs. `denyAll()`

`authenticated()` only requires being logged in, without demanding a specific role. `denyAll()` locks down any route not declared earlier, fitting strict API applications. When using `denyAll()`, account for OIDC login/callback endpoints and required product routes.

Pick the fallback intentionally; never treat `authenticated()` as permission to access all data.

## 14. Sample Controller for Testing URLs

```java
package example.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportExportService exporter;

    public ReportController(ReportExportService exporter) {
        this.exporter = exporter;
    }

    @GetMapping("/api/reports/{id}")
    public String view(@PathVariable long id) {
        return "report-" + id;
    }

    @PostMapping("/api/reports/new")
    public ResponseEntity<Void> create() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    @GetMapping("/api/reports/{id}/export")
    public String export(@PathVariable long id) {
        return exporter.exportReport(id);
    }

    @GetMapping("/api/admin/audit")
    public String audit() {
        return "audit";
    }

    @GetMapping("/public/status")
    public String publicStatus() {
        return "ok";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "profile";
    }
}
```

This is a minimal controller for testing; it omits a database, tenant ownership, validation, and real file streaming. We intentionally place export logic in a service bean to test both the URL layer and the method layer.

## 15. Service Method with `@PreAuthorize`

```java
package example.web;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportExportService {

    @PreAuthorize("hasAuthority('PERM_REPORT_EXPORT')")
    public String exportReport(long reportId) {
        return "export-" + reportId;
    }
}
```

With `@EnableMethodSecurity`, Spring creates method-security interceptors/proxies. When the controller invokes the Spring-managed `ReportExportService` bean, the annotation is enforced.

### 15.1. Method Security Is Not an `if` Inside Source Code

A test calling:

```java
new ReportExportService().exportReport(42L);
```

bypasses the Spring proxy; the annotation **will not be enforced**. Testing method authorization requires obtaining the service from the Spring context or configuring the interceptor properly.

### 15.2. Self-Invocation

If another method in the same object calls:

```java
this.exportReport(42L);
```

it can bypass the Spring proxy in proxy-based method security. Never conclude from a passing controller test that all self-invocations are protected. Design service boundaries so security-annotated methods are called through the proxy or use a supported execution strategy.

## 16. Do Not Forget `@EnableMethodSecurity`

Spring Security 6 uses:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

to enable method security by configuration. If the annotation is missing from the test context or production context, `@PreAuthorize` has no effect just from appearing in source code.

### 16.1. Test Context Must Match Production

If you use `@WebMvcTest(ReportController.class)` without importing method security config or by mocking `ReportExportService`, tests may verify controller responses while **never exercising the real method proxy**.

To test method security, use `@SpringBootTest`/a Spring-managed bean or a slice context that configures the interceptor and service completely. Splitting into a `MockMvc` group for URLs and a service group for `@PreAuthorize` is also a clean approach.

## 17. Integrating Spring Security with `MockMvc`

Two common setups:

**A. Spring Boot test context:**

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportUrlSecurityTest {
    @Autowired MockMvc mockMvc;
}
```

In a standard setup, Spring Boot integrates the filter chain with `MockMvc`.

**B. Standalone/manual `MockMvc` setup:**

```java
MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

If you forget `springSecurity()` in a manual setup, `MockMvc` can invoke controllers without running `SecurityFilterChain`, producing false "200" tests.

### 17.1. Must the Test Context Have a `ClientRegistrationRepository`?

Depending on auto-configuration and security config, `oauth2Login()` may require a `ClientRegistrationRepository`. In tests, you can:

- Define a test client registration with placeholder endpoints and client ID.
- Import the required configuration bean.
- Mock unrelated integrations.
- Use `@WebMvcTest` with proper security config and minimal dependencies.

You do not need a real OP just to test URL authorization with `oidcLogin()`.

## 18. `SecurityMockMvcRequestPostProcessors.oidcLogin()`

Import:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
```

Example:

```java
mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin())
)
.andExpect(status().isForbidden());
```

**Important note:** default `oidcLogin()` supplies Spring Security Test's default fixture authorities; they do not include `PERM_REPORT_READ`. This test demonstrates an authenticated user who lacks the report-read permission under our policy.

### 18.1. Assigning Explicit Authorities

```java
mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin().authorities(
            new SimpleGrantedAuthority("PERM_REPORT_READ")
        ))
)
.andExpect(status().isOk());
```

The data attached by the test post-processor is used to **verify authorization rules**. No OIDC browser redirect, authorization code, or token signature validation is performed by this snippet.

### 18.2. Is `oidcLogin()` the Same as `mockJwt()`?

No. `oidcLogin()` simulates OAuth2/OIDC Login for a web application (Client/RP); `jwt()` in Spring Security Test simulates Bearer JWT authentication for a Resource Server.

When testing an API that accepts Bearer JWTs as a Resource Server, use `jwt()`/`opaqueToken()` and matching Resource Server rules. Never use `jwt()` to test endpoints relying on an OIDC web session, or vice versa, merely because both carry claims.

## 19. Unit Testing the Mapper Directly

The first step in proving claim mapping works is testing `AcmeAuthoritiesMapper` itself.

JUnit 5 example:

```java
package example.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

class AcmeAuthoritiesMapperTest {

    private final AcmeAuthoritiesMapper mapper =
        new AcmeAuthoritiesMapper();

    private OidcIdToken idToken(
            String issuer,
            List<String> groups) {

        return new OidcIdToken(
            "synthetic-token",
            Instant.now(),
            Instant.now().plusSeconds(300),
            Map.of(
                "iss", issuer,
                "sub", "synthetic-user",
                "aud", List.of("acme-client"),
                "groups", groups
            )
        );
    }

    @Test
    void trustedReaderGroupBecomesReadPermission() {
        OidcUserAuthority authority = new OidcUserAuthority(
            idToken(
                "https://login.acme.test/realms/employees",
                List.of("acme-reports-readers")
            )
        );

        var output = mapper.mapAuthorities(List.of(authority));

        assertThat(output)
            .extracting(GrantedAuthority::getAuthority)
            .contains("PERM_REPORT_READ")
            .doesNotContain(
                "PERM_REPORT_WRITE",
                "PERM_REPORT_EXPORT",
                "ROLE_ADMIN"
            );
    }

    @Test
    void unknownGroupDoesNotBecomeAdmin() {
        OidcUserAuthority authority = new OidcUserAuthority(
            idToken(
                "https://login.acme.test/realms/employees",
                List.of("admins", "random-super-admin")
            )
        );

        var output = mapper.mapAuthorities(List.of(authority));

        assertThat(output)
            .extracting(GrantedAuthority::getAuthority)
            .doesNotContain("ROLE_ADMIN");
    }

    @Test
    void sameGroupFromDifferentIssuerDoesNotGrantPermission() {
        OidcUserAuthority authority = new OidcUserAuthority(
            idToken(
                "https://login.other.test/realms/employees",
                List.of("acme-portal-admins")
            )
        );

        var output = mapper.mapAuthorities(List.of(authority));

        assertThat(output)
            .extracting(GrantedAuthority::getAuthority)
            .doesNotContain("ROLE_ADMIN");
    }
}
```

### 19.1. What Was Verified?

- Group allowlist matches for the trusted OP.
- Arbitrary groups cannot elevate to `ROLE_ADMIN`.
- Identical group names from another issuer are not granted permissions.
- The mapper does not grant all permissions by default.

### 19.2. What Was Not Verified?

Self-constructed `OidcIdToken` fixtures do not verify signatures or nonces. This unit test **only verifies the mapper**; it does not prove a real OP issued a valid token or that the mapper bean is wired into the OAuth2 Login pipeline.

## 20. Testing Missing or Empty `groups` Claims

A system must handle:

```json
{"sub": "user-1"}
```

or:

```json
{"sub": "user-1", "groups": []}
```

without granting elevated default permissions.

The test helper should support building an ID Token **without** a `groups` claim. Expected outcomes:

- No `NullPointerException` thrown.
- No `ROLE_ADMIN` granted.
- No fallback from missing groups to strong roles.
- Only policy-permitted authorities (such as specific scopes) are retained.
- Whether to allow login while denying endpoints or reject login outright is an **application policy**.

### 20.1. Claims with Unexpected Data Types

An OP might send `groups="admins"` as a string instead of a list, or nested JSON violating the contract. The mapper should reject/fail gracefully per policy rather than guessing with `String.contains("admin")`. Write tests for malformed claims to prevent privilege escalation through unexpected payloads.

## 21. Testing Duplicate Groups, Ordering, and Casing

Cases:

```text
groups = ["acme-reports-readers", "acme-reports-readers"]
groups = ["ACME-REPORTS-READERS"]
groups = ["acme-reports-readers ", "acme-portal-admins"]
groups = []
```

A mapper backed by a `Set` deduplicates authorities. However, **do not blindly lowercase/trim every group** if the OP contract defines case-sensitive identifiers. If normalization is a business requirement, design it explicitly and test that it never turns a lookalike group into a higher privilege.

### 21.1. Testing Groups Containing Suspicious Characters

Never grant permissions from:

```text
"xx-acme-portal-admins-xx"
"acme-portal-admins,other"
"../../admin"
"ROLE_ADMIN"
```

when policy permits only literal `acme-portal-admins`. An exact-match allowlist prevents substring escalation.

## 22. Writing URL Authorization Tests with `@SpringBootTest`

Example with Spring Boot/JUnit 5:

```java
package example.security;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportUrlSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readerCanReadReport() throws Exception {
        mockMvc.perform(
            get("/api/reports/42")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_READ")
                ))
        )
        .andExpect(status().isOk());
    }

    @Test
    void readerCannotCreateReportEvenWithCsrf() throws Exception {
        mockMvc.perform(
            post("/api/reports/new")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_READ")
                ))
                .with(csrf())
        )
        .andExpect(status().isForbidden());
    }

    @Test
    void writerCanCreateReportWithCsrf() throws Exception {
        mockMvc.perform(
            post("/api/reports/new")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_WRITE")
                ))
                .with(csrf())
        )
        .andExpect(status().isCreated());
    }

    @Test
    void writerWithoutCsrfIsDeniedByCsrfFilter() throws Exception {
        mockMvc.perform(
            post("/api/reports/new")
                .with(oidcLogin().authorities(
                    new SimpleGrantedAuthority("PERM_REPORT_WRITE")
                ))
        )
        .andExpect(status().isForbidden());
    }
}
```

### 22.1. Why Separate the Two POST Tests?

`readerCannotCreateReportEvenWithCsrf` proves **authorization** blocks the reader. Because a valid CSRF token was supplied, the 403 cannot be attributed to missing CSRF.

`writerWithoutCsrfIsDeniedByCsrfFilter` proves CSRF protection is active, **not** that the writer lacks permissions.

A test suite that sends POST requests without `with(csrf())` will return 403 for every role, deceiving the author into thinking POST authorization rules work.

## 23. Testing Anonymous vs. Authenticated Without Permission

For an OAuth2 Login app using browser redirects, anonymous requests to protected URLs typically hit the authentication entry point and redirect to login. They **do not necessarily** return 401 like a Bearer API.

Example:

```java
@Test
void anonymousUserIsAskedToAuthenticate() throws Exception {
    mockMvc.perform(get("/api/reports/42"))
        .andExpect(status().is3xxRedirection());
}

@Test
void authenticatedWithoutReadPermissionGets403()
        throws Exception {

    mockMvc.perform(
        get("/api/reports/42")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_USER")
            ))
    )
    .andExpect(status().isForbidden());
}
```

Condition for the anonymous redirect test: the app uses OAuth2 Login/browser authentication entry point and the security config actually returns 3xx. If the app defines an API-specific entry point returning 401, that is the expected contract. Never hardcode 302 across every app.

### 23.1. Anonymous and 403 Mean Different Things

- Anonymous: authentication absent; normally challenged/redirected to login.
- Authenticated lacking permission: authorization denied; normally 403.
- Authenticated missing CSRF: also 403, yet **a different cause**.
- Invalid Resource Server Bearer token: normally 401 per challenge contract, unlike an OIDC browser session.

Test assertions must reflect **cause and contract**, not merely "status is not 200".

## 24. Testing Admin Role and `ROLE_` Prefix

With rule:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

tests:

```java
@Test
void adminCanReadAudit() throws Exception {
    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")
            ))
    )
    .andExpect(status().isOk());
}

@Test
void authorityNamedAdminWithoutRolePrefixIsNotEnough()
        throws Exception {

    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("ADMIN")
            ))
    )
    .andExpect(status().isForbidden());
}

@Test
void ordinaryReaderCannotReadAudit() throws Exception {
    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ")
            ))
    )
    .andExpect(status().isForbidden());
}
```

Under the default role prefix, these tests demonstrate the exact difference between `hasRole` and `hasAuthority`. If your team customizes the prefix, update expected values per config and test both paths.

## 25. Testing `requestMatchers` Ordering

An easy-to-miss configuration mistake:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
)
```

With the broad matcher first, the admin endpoint may require only authentication. Positive admin tests still pass. You need a **negative test with a regular user**:

```java
@Test
void authenticatedReaderCannotBypassAdminRoute() throws Exception {
    mockMvc.perform(
        get("/api/admin/audit")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ")
            ))
    )
    .andExpect(status().isForbidden());
}
```

If this test returns 200, it signals broken matcher ordering or routing policy.

### 25.1. Add Alternate Paths and Fallbacks

Beyond the exact URL, test:

- `/api/admin/audit`;
- `/api/admin/audit/` if accepted by controller/router;
- URLs with path variables;
- matching GET, POST, PATCH, and DELETE;
- legacy routes/aliases;
- newly added endpoints;
- path normalization per servlet/firewall configuration.

Never disable `StrictHttpFirewall` or loosen path matching just to make tests pass easily; verify the exact accept/reject contract for those paths.

## 26. Testing Method Security Directly via the Spring Bean

With `ReportExportService.exportReport(...)` requiring `PERM_REPORT_EXPORT`:

```java
package example.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import example.web.ReportExportService;

@SpringBootTest
class ReportExportMethodSecurityTest {

    @Autowired
    ReportExportService exporter;

    @Test
    @WithMockUser(authorities = "PERM_REPORT_EXPORT")
    void exporterCanInvokeMethod() {
        assertThat(exporter.exportReport(42L))
            .isEqualTo("export-42");
    }

    @Test
    @WithMockUser(authorities = "PERM_REPORT_READ")
    void readerCannotInvokeMethod() {
        assertThatThrownBy(
            () -> exporter.exportReport(42L)
        )
        .isInstanceOf(AccessDeniedException.class);
    }
}
```

This test uses the Spring-supplied service bean, allowing method-security proxies/interceptors to execute. Depending on your Spring Security version, the thrown exception may be a subtype of `AccessDeniedException`.

### 26.1. What Was Not Tested?

`@WithMockUser` places a mock `Authentication` into the test `SecurityContext`. It does **not** go through OIDC Login or test the claim mapper. This is a **method-policy** test: holding `PERM_REPORT_EXPORT` succeeds, lacking it is blocked.

### 26.2. Why Not Test with `new ReportExportService()`?

Because Spring method security is enforced via a proxy/interceptor, not compiler-injected checks inside the method body. An object instantiated with `new` outside Spring's control can execute the method without throwing `AccessDeniedException`.

## 27. Testing Method-Level Roles and SpEL

Beyond `hasAuthority`, you may see:

```java
@PreAuthorize("hasRole('ADMIN')")
public void manageUsers() { ... }

@PreAuthorize("hasAnyAuthority('PERM_REPORT_READ', 'ROLE_ADMIN')")
public Report getReport(long id) { ... }

@PreAuthorize("#ownerId == authentication.name")
public void updateOwnProfile(String ownerId) { ... }
```

Each expression needs tests for:

- User with sufficient role/authority.
- User lacking role/authority.
- Null/missing arguments if policy handles them.
- Matching/mismatching owner.
- Admin override policy if applicable.
- Spoofed `ownerId` input from a request.

### 27.1. `authentication.name` May Not Be the Business User ID

With OIDC, `authentication.name` may be `sub` or a principal name configured by the mapper/user service. If the domain uses a different internal user ID, comparing `ownerId == authentication.name` directly can be wrong.

Replace it with a policy service checking verified identity mapping, such as `@PreAuthorize("@reportPolicy.canEdit(authentication, #reportId)")`. That bean/method is application-defined and must be tested with realistic tenants and ownership.

## 28. Testing the Intersection of URL and Method Security

Endpoint:

```text
GET /api/reports/42/export
```

must pass:

1. URL rule `GET /api/reports/**` requiring `PERM_REPORT_READ`.
2. Method `ReportExportService.exportReport` requiring `PERM_REPORT_EXPORT`.

Matrix:

| Authorities | URL READ | Method EXPORT | Outcome |
|---|---|---|---|
| None | No | Not invoked | 403 |
| Only `PERM_REPORT_READ` | Yes | No | 403 |
| Only `PERM_REPORT_EXPORT` | No | Not invoked | 403 |
| READ + EXPORT | Yes | Yes | 200 |
| `ROLE_ADMIN` | Depends on role hierarchy/policy | Depends on policy | Does not bypass by default |
| Authenticated with no roles | No | Not invoked | 403 |

Positive test:

```java
@Test
void readAndExportAuthoritiesAreBothRequired() throws Exception {
    mockMvc.perform(
        get("/api/reports/42/export")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ"),
                new SimpleGrantedAuthority("PERM_REPORT_EXPORT")
            ))
    )
    .andExpect(status().isOk());
}
```

Negative test:

```java
@Test
void readerWithoutExportAuthorityGets403() throws Exception {
    mockMvc.perform(
        get("/api/reports/42/export")
            .with(oidcLogin().authorities(
                new SimpleGrantedAuthority("PERM_REPORT_READ")
            ))
    )
    .andExpect(status().isForbidden());
}
```

### 28.1. Tests Must Run the Real Service Proxy

If the controller is tested with a mocked `ReportExportService`, the test may bypass `@PreAuthorize` on the real service and test only URL policy. Use a real Spring-managed service or an appropriate integration test to cover the intersection of both layers.

## 29. Never Let `@WithMockUser` Mask Claim-Mapping Bugs

Test:

```java
@WithMockUser(roles = "ADMIN")
@Test
void adminAccessIsAllowed() { ... }
```

tests role-based authorization. It does not prove the OP group `acme-portal-admins` will be mapped to `ROLE_ADMIN` by the mapper.

You need at minimum:

1. **Mapper test:** `groups=["acme-portal-admins"]` from trusted issuer -> `ROLE_ADMIN`.
2. **URL test:** `ROLE_ADMIN` -> `/api/admin/audit` 200.
3. **Integration wiring test:** real OIDC login with mock OP -> `Authentication` authorities populated as expected.

With only 1 and 2, code could still forget:

```java
.userInfoEndpoint(userInfo -> userInfo.userAuthoritiesMapper(mapper))
```

leaving production never creating `ROLE_ADMIN` even while all unit tests stay green.

## 30. Combining Mapper Output with `oidcLogin()` in Tests

To test the **contract bridging both layers** without a real OP, take the mapper's output and feed it into `oidcLogin()`:

```java
OidcIdToken idToken = // synthetic token fixture
GrantedAuthoritiesMapper mapper = new AcmeAuthoritiesMapper();

var mapped = mapper.mapAuthorities(
    List.of(new OidcUserAuthority(idToken))
);

GrantedAuthority[] authorities =
    mapped.toArray(new GrantedAuthority[0]);

mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin().authorities(authorities))
)
.andExpect(status().isOk());
```

This test proves **the mapper's output is honored properly by the policy**.

**However:** it still does not prove Spring Security OAuth2 Login in the application context actually invokes the mapper. To verify wiring, run an integration test with a mock OP and real login callback, or test the bean configuration explicitly.

## 31. Testing Claims with `oidcLogin().idToken(...)`

`oidcLogin()` lets you customize the fixture ID Token:

```java
mockMvc.perform(
    get("/api/reports/42")
        .with(oidcLogin()
            .idToken(token -> token
                .claim("groups", List.of("acme-reports-readers"))
            )
        )
);
```

This puts `groups` into the test principal's synthetic ID Token.

**Critical warning:** merely adding a `groups` claim does not run `AcmeAuthoritiesMapper` or grant `PERM_REPORT_READ`. To test URL rules, use `.authorities(...)`. To test the mapper, call the mapper directly. To test wiring, run the full login path with a test OP.

This is one of the most important distinctions in this lesson.

## 32. `oauth2Login()` and `oidcLogin()` Differ

Spring Security Test supports two directions:

**`oauth2Login()`**

- Simulates an OAuth2 Login principal.
- Appropriate when the provider uses non-OIDC OAuth2 login without an ID Token.
- Supports configuring authorities and OAuth2 user attributes.

**`oidcLogin()`**

- Simulates an OpenID Connect Login principal.
- Includes OIDC ID Token/UserInfo fixtures.
- Supports configuring authorities on `Authentication`.

In both cases, the test post-processor builds a simulated context; neither calls an OP, Authorization Endpoint, Token Endpoint, or UserInfo endpoint.

### 32.1. Do Not Treat `OAuth2User` Claims the Same as `OidcUser`

A non-OIDC OAuth2 provider supplies `OAuth2UserAuthority` with attributes differing from `OidcUserAuthority`. A mapper handling only `OidcUserAuthority` will not map roles for plain OAuth2 Login.

If your product supports both, maintain separate mapping policies per provider/registration and test both paths.

## 33. Resource Server JWT Tests Do Not Replace OIDC Client Tests

A backend can simultaneously be:

- An OIDC Client/RP for browser login.
- An OAuth2 Resource Server accepting JWT Bearer tokens for APIs.

The two `Authentication` types differ:

| Flow | Typical `Authentication` | Appropriate test post-processor |
|---|---|---|
| Browser OIDC Login | `OAuth2AuthenticationToken` with `OidcUser` | `oidcLogin()` |
| Non-OIDC OAuth2 Login | `OAuth2AuthenticationToken` with `OAuth2User` | `oauth2Login()` |
| Resource Server JWT | `JwtAuthenticationToken` | `jwt()` |
| Resource Server opaque token | Bearer authentication with token introspection | `opaqueToken()` |
| Form login/username/password | Authentication with `UserDetails` | `user()` or `@WithMockUser` |

A `jwt().authorities(...)` test may be valid for a REST Resource Server, yet **does not prove** `OidcUser` authorities are produced per OIDC Login policy.

If the same URL supports both browser sessions and Bearer tokens, test both authentication entry points/filter chains per contract.

## 34. Role Hierarchy: Does `ADMIN` Automatically Receive `REPORT_READ`?

Not every admin role receives all permissions by default. If the app configures a `RoleHierarchy`, such as ADMIN inheriting VIEWER, policies and tests must reflect that hierarchy.

Principles:

- Enforce authorization from the real hierarchy configuration, never assuming from the string `ROLE_ADMIN`.
- If `ROLE_ADMIN` should be permitted to export reports, define an explicit policy.
- Role hierarchies and `PERM_*` permissions may follow different semantics.
- Test a user holding the admin role **without** the export permission to verify the actual contract.
- Never hardcode 200 for every admin test without checking authorities/roles at each layer.

### 34.1. Prefix Mismatch in Hierarchies

If a hierarchy specifies `ROLE_ADMIN > ROLE_VIEWER` while a test supplies `ADMIN`, results may diverge. Test the exact strings produced post-mapping and the policy methods using `hasRole`/`hasAuthority`.

## 35. Multi-Tenancy: Right Role, Wrong Tenant

Scenario:

```text
Tenant A (Acme):
  issuer = https://login.acme.test/realms/employees
  group = acme-portal-admins
  user = alice

Tenant B (Globex):
  issuer = https://identity.globex.test/oidc
  group = globex-portal-admins
  user = bob
```

Alice holds `ROLE_ADMIN` **for Acme**, which does not grant admin rights over Globex.

A URL rule like:

```java
.requestMatchers("/t/*/admin/**").hasRole("ADMIN")
```

can be overly broad if `ROLE_ADMIN` carries no tenant context. Add policy ensuring the principal is a member/admin of **the specific tenant being accessed**, such as a custom authorization manager or service check.

### 35.1. URL Variables Are Not Proof of Tenant Membership

```text
GET /t/globex/admin/users
```

is a caller-chosen request path. Never take `globex` from the URL and grant access simply because a token holds `ROLE_ADMIN` in another tenant.

### 35.2. Testing Cross-Tenant Denial

Create cases:

| Identity | Authorities | Request tenant | Expectation |
|---|---|---|---|
| Alice of Acme | Acme admin | Acme | Allow if policy satisfied |
| Alice of Acme | Acme admin | Globex | Deny |
| Bob of Globex | Globex admin | Globex | Allow |
| Bob of Globex | Globex admin | Acme | Deny |
| User without membership | Role string from another claim | Acme/Globex | Deny |
| Same `sub` across two issuers | Any | Non-matching tenant | No improper account linking |

This tests application authorization, not merely `hasRole("ADMIN")`.

## 36. Designing Resource-Based Method Authorization

A static permission is not always enough. For instance, `PERM_REPORT_READ` may apply only to reports belonging to the user's tenant.

You can build a policy bean:

```java
@Service("reportPolicy")
public class ReportPolicy {

    private final ReportRepository reports;
    private final TenantMembershipService membership;

    public boolean canRead(
            Authentication authentication,
            long reportId) {

        // Look up the report's tenant from a trusted data source.
        // Map Authentication -> internal user via issuer+sub.
        // Verify membership/permission inside the report's tenant.
        // Illustrative pseudocode:
        return verifiedCanRead(authentication, reportId);
    }
}
```

And:

```java
@PreAuthorize("@reportPolicy.canRead(authentication, #reportId)")
public Report getReport(long reportId) {
    // ...
}
```

`verifiedCanRead` is application-implemented business logic, not a Spring Security API. In production, the method must fail closed whenever identity mapping, tenant lookup, or authority sources cannot be verified.

### 36.1. Test URL and Business Policies Separately

- URL test: anonymous/users lacking global read authority are blocked.
- Method test: users holding global read authority without tenant membership are still blocked.
- Repository test: report IDs belonging to another tenant are never exposed.
- Race/revocation test: permissions revoked during an active session are revalidated within the product's committed SLA.

## 37. Testing Claim-Mapping Failures to Prevent Privilege Escalation

A negative matrix should include:

| Simulated input | Expectation |
|---|---|
| `groups=[]` | No group-derived roles created |
| Missing `groups` | No strong roles granted automatically |
| `groups="acme-portal-admins"` (violates list schema) | Per policy: reject/unmapped, never elevate |
| `groups=["admins"]` | Fails allowlist |
| `groups=["acme-portal-admins-extra"]` | Fails exact group match |
| Matching group, wrong issuer | Does not grant Acme role |
| Same `sub` from another issuer | Not treated as the same user |
| Email `@acme.test` without membership | No automatic grant |
| Duplicate group claim twice | No duplicate authority side effects |
| Null/missing principal | Sensitive actions denied |
| OP UserInfo changes shape | Never silently fall back to admin |
| Arbitrary claim named `role=ADMIN` | Ignored unless backed by trusted policy |

Test **near-match** inputs too, as they expose substring or case-insensitive mapping bugs.

## 38. Method Security Can Be Bypassed When Tests Mock the Service

Suppose `ReportController` calls:

```java
reportExportService.exportReport(id);
```

If `@WebMvcTest` uses a mock bean returning `"export-42"`, `@PreAuthorize` on the real implementation is not necessarily executed. The controller test can return 200 even though the production service would deny access.

A sound split:

1. MockMvc controller slice tests for HTTP routing, serialization, and URL authorization.
2. Service bean integration tests for method authorization.
3. A full-context test containing both the controller and the real Spring-managed service to verify the intersection of both layers.

### 38.1. You Do Not Need One Test to Replace All Three

One broad test can catch many issues, yet is slower and harder to debug. Use focused contract tests alongside representative integration cases for high-risk paths.

## 39. Testing Real Spring Security Configuration

An app may have multiple `SecurityFilterChain` beans:

```text
Chain 1: /api/**      -> Bearer Resource Server
Chain 2: /**          -> OAuth2 Login browser session
```

Or a single chain supporting multiple authentication methods. If `@WebMvcTest` imports only a subset, MockMvc may not apply the same chain matchers as production.

### 39.1. Questions to Verify

- Is chain `@Order` right?
- Does the chain's request matcher capture the endpoint?
- Does the URL rule reside in that chain?
- Is CSRF enabled/disabled matching each endpoint's contract?
- How does the authentication entry point handle anonymous users?
- Can OIDC Login initiate and handle callbacks within the chain?
- Are method security beans active?
- Are new URLs tested so they aren't swallowed by a broad rule?

Never use `addFilters=false` when testing URL authorization; that flag strips out the very `SecurityFilterChain` under test.

## 40. Testing Service Authorization with `@Async`, `@Transactional`, or Schedulers

Method security typically relies on proxies and `SecurityContext`. When a method runs asynchronously or on a scheduler:

- `SecurityContext` may not propagate to the new thread.
- `@PreAuthorize` may run before or inside the async invocation depending on proxy/config.
- A service calling its own annotated method can bypass the proxy.
- Background jobs may lack a user `Authentication`.
- Argument-based authorization needs a session-independent source of truth when running offline.

Tests should exercise the real execution context. Never assume a synchronous `@WithMockUser` test guarantees behavior inside an executor or scheduler.

### 40.1. Never "Fix a Test" by Removing `@PreAuthorize`

If a permission check fails in a background job, design proper service-account/delegated authorization; never delete the annotation just to let the batch job run.

## 41. Revoked Permissions and Stale `Authentication`

When a user logs in, authorities may be computed and stored in `SecurityContext`/session. If an admin revokes `ROLE_ADMIN`, existing `Authentication` objects do not update automatically.

Therefore:

- Testing that the mapper works at login time **does not prove** revoked permissions are blocked immediately afterward.
- When permission freshness is required, implement session invalidation, permission reloading, or dynamic authorization checks.
- Test an existing session after a role change to verify the SLA.
- For JWT APIs, test expiry, introspection, and denylists separately.
- Do not confuse an OIDC Login session principal with a Resource Server access token.

### 41.1. Testing Stale Roles

Scenario:

1. User logs in and receives `ROLE_ADMIN`.
2. Admin removes the group/membership from the source of truth.
3. The session cookie remains valid.
4. User calls an admin endpoint.
5. Application must enforce policy: deny immediately, deny after TTL, or require re-login per SLA.

A test that logs in fresh after role removal misses stale-authority bugs in existing sessions.

## 42. Testing Missing CSRF Tokens

On the Servlet stack, CSRF is typically enabled for state-changing methods in session-based web apps.

Table:

| Request | Authentication | CSRF | Permission | Expected |
|---|---|---|---|---|
| GET report | Reader | Not needed for GET by default | READ | 200 |
| POST create report | Writer | Valid | WRITE | 201 |
| POST create report | Writer | Missing | WRITE | 403 due to CSRF |
| POST create report | Reader | Valid | Missing WRITE | 403 due to authorization |
| POST create report | Anonymous | Valid | None | Challenge/deny per entry point |
| DELETE a resource | Authorized | Missing | Yes | Typically rejected by CSRF if CSRF applies |

Never assert 403 alone and conclude permission policy is working. Separate CSRF tests from role tests by providing a valid CSRF token whenever testing authorization.

### 42.1. With Stateless Bearer APIs

Some stateless Resource Server APIs do not use browser sessions/cookies and are designed to omit CSRF on matching endpoints. In that case the test matrix differs. Never disable CSRF across the entire OIDC web login app just because Bearer APIs are configured as stateless.

## 43. When to Use `@WithMockUser` vs. `oidcLogin()`?

| Tool | Best suited for | Does not test |
|---|---|---|
| `@WithMockUser` | Unit/integration tests of Spring method security, authority-based policy | OIDC claim mapping / remote login |
| `with(user(...))` | MockMvc requests with explicit username/authorities | OP token validation |
| `with(oidcLogin())` | OIDC Client URL rules, principal shape, authorities | Authorization code flow, default mapper wiring |
| `with(oauth2Login())` | Non-OIDC OAuth2 Login rules | OIDC ID Token processing |
| `with(jwt())` | Resource Server JWT authorization rules | OIDC browser login |
| Mock OP + login callback | End-to-end OIDC config, mapper wiring, validation | Some external provider behaviors outside the mock |

Pick the tool matching the question the test aims to answer. You do not need a mock OP for every `hasAuthority` rule, yet you cannot rely solely on `oidcLogin()` to prove production group mapping.

## 44. Integrating Authorization Rules Across HTTP Methods

Do not test only GET and POST. A real system may define:

```text
GET    /api/reports/{id}            -> READ
POST   /api/reports/new             -> WRITE
PUT    /api/reports/{id}            -> WRITE
PATCH  /api/reports/{id}/status     -> APPROVE
DELETE /api/reports/{id}            -> DELETE
GET    /api/reports/{id}/export     -> READ + EXPORT
```

Every HTTP method needs explicit rules. With a fallback `.anyRequest().authenticated()`, a new DELETE endpoint might require only login if a developer forgets to declare the DELETE permission.

### 44.1. Negative Tests for New Operations

Add test:

```java
mockMvc.perform(
    delete("/api/reports/42")
        .with(oidcLogin().authorities(
            new SimpleGrantedAuthority("PERM_REPORT_READ")
        ))
        .with(csrf())
)
.andExpect(status().isForbidden());
```

Expecting 403 only passes if security policy **genuinely** denies readers on DELETE. If a DELETE matcher is missing and falls back to `authenticated()`, this test catches the vulnerability.

## 45. Return Status Alone Is Not Enough to Prove Method Protection

Suppose the export endpoint returns 403 because the controller checks a business condition itself while `@PreAuthorize` never actually ran. A test asserting 403 still passes without showing the security interceptor executed.

To test method authorization:

- Invoke the Spring bean directly through its proxy with an `Authentication` lacking the permission.
- Assert `AccessDeniedException` per contract.
- On the positive case, assert the business return value.
- Optionally mock downstream dependencies to confirm sensitive logic is not called when denied.
- Test self-invocation/alternate callers if the architecture allows them.

Never treat an arbitrary HTTP response body as sole proof of an authorization mechanism.

## 46. Logging Test Results Without Leaking Tokens

Even test fixtures should follow strict hygiene:

- Use synthetic ID Tokens and access tokens.
- Never copy production tokens into test sources.
- Never print `Authorization`, `Cookie`, or `OAuth2AuthorizedClient` in logs.
- Never log full OIDC claims if they contain PII.
- Never include `code`/`state` from URLs in CI artifacts unless using approved synthetic fixtures.
- Tie test failures to route templates, registration IDs, and policy identifiers rather than raw tokens.

With MockMvc, `andDo(print())` prints request/response details to test output. In environments with real credentials or test secrets, restrict or sanitize output before using it.

## 47. Lab A — Testing `GrantedAuthoritiesMapper`

**Goal:** convert OIDC groups into permissions via an allowlist.

1. Create `AcmeAuthoritiesMapper` with four group mappings.
2. Build synthetic OIDC ID Tokens for the Acme issuer.
3. Verify the reader group produces `PERM_REPORT_READ`.
4. Verify the writer group does not grant `ROLE_ADMIN`.
5. Verify the admin group produces exact `ROLE_ADMIN`.
6. Verify unknown/missing groups grant no permissions.
7. Verify identical groups from another issuer are ignored.
8. Verify duplicate groups do not create duplicate authorities.

**Expected outcome:** the mapper grants no extra permissions from unapproved inputs.

## 48. Lab B — MockMvc with `oidcLogin()`

**Goal:** verify URL policies for authenticated users.

1. Configure URL rules for GET READ, POST WRITE, and admin role.
2. Use `oidcLogin().authorities(PERM_REPORT_READ)`.
3. GET report -> 200.
4. POST report with valid CSRF -> 403.
5. Use `oidcLogin().authorities(PERM_REPORT_WRITE)`.
6. POST report with CSRF -> 201.
7. POST report without CSRF -> 403, caused by CSRF.
8. Use `ROLE_ADMIN` to access admin -> 200.

**Expected outcome:** tests clearly distinguish authentication, authorization, and CSRF.

## 49. Lab C — `@PreAuthorize` Through the Proxy

**Goal:** ensure method authorization cannot be bypassed.

1. Create Spring-managed `ReportExportService`.
2. Enable `@EnableMethodSecurity`.
3. Annotate with `@PreAuthorize("hasAuthority('PERM_REPORT_EXPORT')")`.
4. Test with `@WithMockUser(authorities = "PERM_REPORT_EXPORT")` -> succeeds.
5. Test with READ only -> `AccessDeniedException`.
6. Compare against calling an instance created with `new` to observe the proxy boundary.
7. Create a controller invoking the real service bean.
8. Verify GET export requires both READ and EXPORT in an HTTP integration test.

**Expected outcome:** annotations are enforced at the Spring proxy and both URL and method layers operate.

## 50. Lab D — Matcher Order and Endpoint Bypass

**Goal:** detect overly broad rules.

1. Write rule `/api/admin/**` requiring `ROLE_ADMIN`.
2. Test reader accessing admin -> 403.
3. Temporarily flip the order, putting `/api/**.authenticated()` first in a test branch.
4. Re-run the reader test and observe the vulnerability.
5. Restore the safe ordering.
6. Add POST/DELETE endpoint tests.
7. Test `authenticated()` vs. `denyAll()` fallbacks per product contract.
8. Document rule precedence and keep regression tests.

**Expected outcome:** negative tests catch broken matcher ordering that positive admin tests miss.

## 51. Lab E — `groups` Claim Does Not Auto-Map with `oidcLogin()`

**Goal:** understand the boundaries of Spring Security Test post-processors.

1. In MockMvc, use `oidcLogin().idToken(token -> token.claim("groups", ...))`.
2. Omit `.authorities(...)`.
3. Observe that the authorization rule requiring `PERM_REPORT_READ` is not automatically satisfied in this lab.
4. Call the mapper directly with an `OidcUserAuthority` carrying the group claim.
5. Verify the mapper produces `PERM_REPORT_READ`.
6. Pass the mapper's output via `.authorities(...)`.
7. GET report -> 200.
8. Note that a full login integration test is needed to verify mapper bean wiring.

**Expected outcome:** claim fixtures and `GrantedAuthority` fixtures are two separate inputs.

## 52. Lab F — Multi-Tenant Role Isolation

**Goal:** prevent one tenant's permissions from working in another tenant.

1. Define distinct Acme and Globex issuers.
2. Create an Acme user with the admin group.
3. Ensure the mapper accepts Acme groups only for the matching issuer.
4. Test the mapper with the same group under the Globex issuer.
5. Build a policy verifying internal account tenant membership.
6. Acme admin calls Acme admin API -> allow.
7. Same user calls Globex admin API -> deny.
8. Test that matching emails/`sub` across issuers do not auto-link.

**Expected outcome:** `ROLE_ADMIN` does not become "global SaaS admin" outside its scope.

## 53. Lab G — Spring Security Test and Mock OP

**Goal:** separate authorization policy tests from login-wiring integration tests.

1. Run MockMvc tests with `oidcLogin()` for URL rules.
2. Run `GrantedAuthoritiesMapper` unit tests.
3. Stand up a fake OP with Issuer/JWKS/Authorization/Token endpoints.
4. Initiate RP Authorization Code/OIDC Login using the test registration.
5. Return a valid ID Token containing the Acme reader group.
6. Observe the post-login `Authentication` carries the expected authority.
7. Return an ID Token with the admin group from the wrong issuer/audience and verify rejection.
8. Confirm the mapper configured in `oauth2Login().userInfoEndpoint()` actually ran.

**Expected outcome:** the entire path claims -> `Authentication` -> HTTP policy works end-to-end, not just manual authority mocking.

## 54. Lab H — Testing Revoked Permissions While a Session Remains Alive

**Goal:** catch stale authorities.

1. User completes OIDC login and holds `ROLE_ADMIN`.
2. Store `Authentication` in the RP HTTP session.
3. Remove the group/membership at the source of truth.
4. Keep the old session and call the admin endpoint.
5. Observe current behavior per design: the session may still retain old authorities.
6. Add permission freshness checks or session invalidation per policy.
7. Re-test after revocation; must meet SLA.
8. Never infer from a rejected fresh re-login that existing sessions are automatically revoked.

**Expected outcome:** authorization freshness is verified independently of mapper correctness.

## 55. Comprehensive Testing Matrix

| Test | Input | Expectation |
|---|---|---|
| Trusted reader group | Valid ID Token group | READ authority |
| Trusted writer group | Valid ID Token group | WRITE authority |
| Trusted exporter group | Valid ID Token group | EXPORT authority |
| Trusted admin group | Valid ID Token group | `ROLE_ADMIN` |
| Missing groups | No `groups` claim | No auto-granted permissions |
| Unknown groups | Group outside allowlist | No permissions granted |
| Wrong issuer | Same group from another issuer | No Acme rights granted |
| Duplicate groups | Same group listed twice | Authorities not duplicated |
| Malformed claim | String instead of list | No privilege escalation |
| Same `sub`, different issuer | Subject collision | No auto-linking |
| Anonymous GET | No `Authentication` | Redirect/challenge per entry point |
| Reader GET report | READ | 200 |
| Reader POST report + CSRF | READ | 403 |
| Writer POST report + CSRF | WRITE | 201 |
| Writer POST report without CSRF | WRITE | 403 due to CSRF |
| Reader admin endpoint | READ | 403 |
| Admin admin endpoint | `ROLE_ADMIN` | 200 |
| `ADMIN` authority missing prefix | `ADMIN` | 403 under default `hasRole` |
| Export with READ only | READ | 403 at method |
| Export with EXPORT only | EXPORT | 403 at URL |
| Export with READ + EXPORT | Both | 200 |
| Service method with EXPORT | `@WithMockUser` EXPORT | Succeeds |
| Service method with READ only | `@WithMockUser` READ | `AccessDeniedException` |
| Missing `@EnableMethodSecurity` | Test context lacks proxy | Test catches misconfiguration |
| Mocked service bypass | `@WebMvcTest` mocks service | Not used as proof of method policy |
| Broken matcher order | Broad rule before admin rule | Negative test catches failure |
| Alternative HTTP methods | DELETE/PATCH | Rules match operation |
| Cross-tenant admin | Acme role, Globex request | Deny |
| Revoked role | Old session remains | Denied per SLA policy |
| `oidcLogin` claims only | Group claim without authorities | Never assumed mapper ran |
| Full OP login | ID Token group test | Real mapper wiring executed |
| Resource Server JWT | `jwt()` fixture | Separate JWT policy test |

## 56. Common Error Troubleshooting Table

| Symptom | Possible cause | Resolution |
|---|---|---|
| `oidcLogin()` returns 403 despite `groups` in token | Claims fixture does not auto-map authorities | Call mapper directly or set `.authorities(...)` |
| Mapper unit test passes yet real login lacks role | `userAuthoritiesMapper`/custom user service not wired | Test real login pipeline |
| `hasRole("ADMIN")` always 403 | Authority is `ADMIN` instead of `ROLE_ADMIN` | Check prefix/config |
| POST always 403 even for writer | Missing CSRF token | Add `with(csrf())` when testing authorization |
| GET admin returns 200 for regular user | Broad request matcher precedes admin matcher | Fix ordering and add negative tests |
| `@PreAuthorize` has no effect | `@EnableMethodSecurity` not enabled | Enable right config/test context |
| `@PreAuthorize` works in service test yet controller bypasses | Mocked service or self-invocation | Inspect proxy/integration |
| Calling service via `new` is not denied | Bypassed Spring proxy | Inject bean from Spring context |
| User from another tenant still gets `ADMIN` | Mapping ignores issuer/tenant | Add membership/authorization check |
| `jwt()` test passes, OIDC session test fails | Confusing Resource Server with OIDC Client `Authentication` | Test matching principal type |
| `@WithMockUser` passes yet real ID Token fails | Bypassed protocol/mapping validation | Write mock OP integration test |
| Anonymous returns 302 instead of 401 | OAuth2 Login browser entry point | Assert per security contract |
| Export method with EXPORT gets 403 | URL layer also requires READ | Check both layers |
| Method test returns 403 from business check | Real interceptor not tested | Call Spring bean directly / verify `AccessDeniedException` |
| Authority removed at OP yet session stays admin | Stale `Authentication` | Invalidate session or revalidate |
| Same group at another issuer still grants role | Mapper only checks group name | Add issuer/registration context |
| New DELETE route open to every logged-in user | Overly broad `authenticated()` fallback | Declare operation-specific matchers |
| Path bypass behavior in MockMvc differs from prod | Context/filter/firewall mismatch | Use production-like configuration |

## 57. Misconceptions to Avoid

| Misconception | Accurate understanding |
|---|---|
| "A valid ID Token means the user can access every endpoint." | OIDC authenticates identity; authorization is decided by policy. |
| "Group `admins` is always `ROLE_ADMIN`." | Must rely on trusted issuer/tenant allowlists. |
| "Scopes and roles are the same thing." | `SCOPE_*` and `ROLE_*` are distinct authorities. |
| "`hasRole('ADMIN')` checks authority `ADMIN`." | Under the default prefix, it checks `ROLE_ADMIN`. |
| "`oidcLogin().idToken(groups)` runs the mapper." | The post-processor simulates `Authentication`; it does not run mapper wiring. |
| "`oidcLogin()` proves the ID Token signature is valid." | It bypasses remote protocol validation. |
| "`@WithMockUser` tests OIDC claims." | It only sets a mock `Authentication`. |
| "One 200 test for admin proves the API is secure." | You need negative tests for under-privileged users, anonymous access, and bypass routes. |
| "POST 403 proves the permission policy works." | 403 can come from the CSRF filter. |
| "`@PreAuthorize` always works just by adding the annotation." | Requires enabled method security and Spring proxy invocation. |
| "Calling a method with `new` equals calling via a Spring bean." | Calling `new` bypasses the interceptor/proxy. |
| "Mocking a service in an MVC test proves `@PreAuthorize`." | The mock can skip the method security implementation. |
| "`ROLE_ADMIN` from tenant A is admin for tenant B." | Tenant-scoped authorization is required. |
| "UserInfo/ID Token group mapping works identically across providers." | Claim shape/source depends on each OP contract. |
| "Changing OP permissions immediately updates the active `SecurityContext`." | Sessions can hold stale authorities. |
| "Resource Server `jwt()` equals OIDC Client `oidcLogin()`." | They represent two different authentication flows. |
| "Matcher order does not matter." | An earlier broad rule can shadow a later specific rule. |
| "No need to test HTTP methods other than GET." | POST/PUT/PATCH/DELETE have distinct permissions and CSRF semantics. |

## 58. Self-Check Questions

**Q1.** How does `GrantedAuthority` differ from an OIDC group claim?

*Hint:* a group is data from the OP; an authority is a permission the application uses in authorization decisions.

**Q2.** Are `hasRole("ADMIN")` and `hasAuthority("ROLE_ADMIN")` equivalent under the default prefix?

*Hint:* typically yes, though custom prefix configuration can change this.

**Q3.** Why should mapper unit tests and MockMvc URL tests be kept separate?

*Hint:* one tests mapping; the other tests enforcement of existing authorities.

**Q4.** Does `oidcLogin().idToken(token -> token.claim("groups", ...))` invoke the mapper automatically?

*Hint:* no.

**Q5.** Why must the reader POST test send `with(csrf())`?

*Hint:* we want 403 due to missing WRITE, not missing CSRF token.

**Q6.** Why might an anonymous request in an OIDC browser app return 302 instead of 401?

*Hint:* the authentication entry point redirects the browser to login.

**Q7.** Why is `new ReportExportService().exportReport(...)` a poor way to test `@PreAuthorize`?

*Hint:* it bypasses the Spring-managed method-security proxy.

**Q8.** What happens if `@EnableMethodSecurity` is in production yet missing from the test context?

*Hint:* method authorization tests may fail to reflect production behavior.

**Q9.** Why is a user with EXPORT but without READ still denied on GET export?

*Hint:* URL authorization requires READ before the service method checks EXPORT.

**Q10.** If the same `sub=123` appears from two issuers, can they be treated as the same user?

*Hint:* no; `sub` is issuer-scoped.

**Q11.** If a role is ADMIN for tenant Acme, does the user automatically become admin of Globex?

*Hint:* no; tenant membership and permissions must be enforced separately.

**Q12.** Does a `@WebMvcTest` using a mocked export service prove method security?

*Hint:* not necessarily.

**Q13.** Why does a `jwt()` test not prove the OIDC Login authority mapper works?

*Hint:* Resource Server JWT authentication is a different flow.

**Q14.** When an admin removes a group while an HTTP session remains alive, what must be tested?

*Hint:* stale authorities and authorization freshness inside the session.

**Q15.** What risk arises when `/api/**.authenticated()` precedes `/api/admin/**.hasRole("ADMIN")`?

*Hint:* the broad rule can short-circuit the admin rule.

## 59. Checklist Before Considering Authorization Tests Complete

1. **Policy documented:** Does every endpoint/method have defined permissions and expected statuses?
2. **Source trust:** Does claim mapping trust only approved providers/issuers/tenants?
3. **Allowlist groups:** No substring matching or fallback to admin?
4. **Authority names:** Are `ROLE_*`, `SCOPE_*`, and `PERM_*` consistent?
5. **Mapper tests:** Are valid, invalid, missing, duplicate, and wrong-issuer group cases covered?
6. **Wiring tests:** Is the mapper/custom `OidcUserService` proven to be invoked during real login?
7. **MockMvc security:** Is the filter chain active in the test context?
8. **Positive/negative:** Are both authorized and under-privileged authenticated tests present per route?
9. **Anonymous:** Is entry-point behavior (302/401) tested per contract?
10. **CSRF:** Do tests distinguish 403 due to CSRF from 403 due to authorization?
11. **Matcher order:** Is a regular user tested and blocked from accessing admin routes?
12. **HTTP methods:** Are GET/POST/PUT/PATCH/DELETE tested per declared policy?
13. **Method security:** Is `@EnableMethodSecurity` truly enabled and invoked via a Spring proxy?
14. **Proxy boundaries:** Are tests free from self-invocation or `new`-instantiation illusions?
15. **Intersection:** Is URL READ + method EXPORT tested across all four combinations?
16. **Tenancy:** Can a tenant A role access tenant B?
17. **Session freshness:** Do revoked roles take effect within the committed timeframe?
18. **Wrong auth type:** Is `jwt()` kept out of OIDC Client tests outside Resource Server contexts?
19. **Sensitive logs:** Do tests avoid printing real tokens, ID Token claims, CSRF tokens, or session cookies?
20. **Regression:** Does every new endpoint have matching allow/deny policy tests?

## 60. References

- [Spring Security Reference — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): integrating Spring Security with Servlet tests.
- [Spring Security Reference — MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): configuring MockMvc and Spring Security filters.
- [Spring Security Reference — MockMvc OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oauth2Login()`, `oidcLogin()`, and test authentication fixtures.
- [Spring Security Reference — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): using the CSRF request post-processor.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): URL authorization, request matchers, and rule ordering.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and interceptors.
- [Spring Security Reference — OAuth 2.0 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): user authorities mapper and `OidcUserService` customization.
- [Spring Security API — GrantedAuthoritiesMapper](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/mapping/GrantedAuthoritiesMapper.html): authority mapping contract.
- [Spring Security API — OidcUserAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html): ID Token/UserInfo and OIDC authority.
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html): `Authentication` for OAuth2/OIDC Login.
- [Spring Security API — OidcIdToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/OidcIdToken.html): synthetic ID Token fixtures.
- [Spring Security Test API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): `oidcLogin()`, `oauth2Login()`, `jwt()`, and `csrf()`.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `SpringBootTest` and `AutoConfigureMockMvc`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Tokens, UserInfo, issuer, subject, and authentication.
- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): OAuth2 authorization grants and scopes.
- [RFC 9700 — OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): securing authorization, tokens, and Client integrations.

**Conclusion:** Testing authorization in a Spring Security OIDC Client application requires proving **the entire chain from claims to authorities and from authorities to permitted actions**. Test `GrantedAuthoritiesMapper` to ensure only trusted groups become `ROLE_*` or `PERM_*`; use `MockMvc + oidcLogin().authorities(...)` to verify URL rules, HTTP methods, matcher ordering, anonymous access, and CSRF; and use Spring-managed services with `@EnableMethodSecurity` to verify `@PreAuthorize` is genuinely enforced through proxies. Never treat `oidcLogin()` as proof the mapper runs in production, never treat a CSRF 403 as proof of permission denial, and never overlook tenant membership or stale session authorities. A strong test suite includes **allow and deny cases** at every layer, especially scenarios risking privilege escalation or cross-tenant data leaks.
