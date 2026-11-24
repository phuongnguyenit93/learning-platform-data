# GrantedAuthoritiesMapper and Converting Claims to Application Permissions

**Module:** Spring Security – Servlet  
**Parent topic:** OAuth2 Client

## 1. The problem: OAuth2/OIDC login does not mean application permissions

A Spring Security Servlet application can log users in via **OAuth 2.0 Login / OpenID Connect (OIDC)**. After a user logs in through an Identity Provider (IdP), the application has an `Authentication` object containing a principal and a set of `GrantedAuthority`. However, information provided by the IdP such as `sub`, `email`, `groups`, `roles`, `scope`, or custom claims **does not automatically become business permissions** like `ROLE_ADMIN`, `ROLE_EDITOR`, or `ORDER_APPROVE`.

**GrantedAuthoritiesMapper** is the extension point that lets an application **map authorities obtained after OAuth2/OIDC login** into `GrantedAuthority` instances understood by Spring Security's authorization mechanisms.

Example internal policy:

| Trusted claim from IdP | Authority in application | Permitted action |
| --- | --- | --- |
| `app_roles: ["viewer"]` | `ROLE_VIEWER` | View viewer pages |
| `app_roles: ["editor"]` | `ROLE_EDITOR` | Edit per application policy |
| `app_roles: ["admin"]` | `ROLE_ADMIN` | Access administrative endpoints |
| `app_roles: ["unknown"]` | Do not auto-grant a new role | Reject undefined roles |
| No `app_roles` | Add no business roles | Can only log in, no privilege elevation |

Even if a user has `ROLE_ADMIN`, an endpoint operating on a specific object may still need permission checks for **tenant, project, owner, status, and resource**. A role is one authorization factor, not a replacement for complete checks.

## 2. Distinguishing OAuth2 Client, OIDC, access tokens, and application permissions

Spring Security supports several OAuth 2.0 scenarios, but how claims become permissions differs:

- **`oauth2Login()` (Servlet OAuth2 Client):** the web app redirects the browser to the IdP, receives the login result, builds an `OAuth2AuthenticationToken` / principal, and usually stores authentication in the HTTP session. `GrantedAuthoritiesMapper` fits **user authorities after login**.
- **OIDC login:** uses the `openid` scope and ID Token to verify identity. `OidcUserAuthority` can hold `OidcIdToken` and `OidcUserInfo` (if available).
- **Non-OIDC OAuth2 login:** user info typically comes from the UserInfo endpoint; `OAuth2UserAuthority` carries attributes returned by the provider.
- **OAuth2 Resource Server receiving JWT bearer tokens:** the usual path is `JwtAuthenticationConverter` / `JwtGrantedAuthoritiesConverter`, **not `oauth2Login`'s `GrantedAuthoritiesMapper`**.
- **OAuth2 Client app calling another API:** `OAuth2AuthorizedClient`/access token is used to call a downstream resource server; the logged-in user's authorities do not automatically determine permissions at the downstream API.
- **Client credentials (machine-to-machine):** has no user login flow to use a mapper as in this example.

A **Claim** is an information field inside an ID token or UserInfo response, for example:

~~~json
{
  "sub": "user-123",
  "preferred_username": "an",
  "app_roles": ["viewer", "editor"]
}
~~~

This is an **example claim agreed upon between the IdP and application**. No OIDC standard requires every IdP to emit `app_roles`; some IdPs use `roles`, `groups`, namespaced claims, `realm_access.roles`, or a separate authorization API. You must confirm **whether the actual claim lives in the ID Token, UserInfo, or only in the Access Token** before writing a mapper.

### 2.1. Scope is not an application role

Spring Security can create authorities like `SCOPE_email`, `SCOPE_profile`, or `SCOPE_xxx` from related scopes. A scope describes the granted permissions in an OAuth2 relationship; it does not state that the user is an application administrator.

- `hasRole("ADMIN")` by default checks for the **`ROLE_ADMIN`** authority.
- `hasAuthority("ROLE_ADMIN")` checks for the exact string `ROLE_ADMIN`.
- `hasAuthority("SCOPE_orders.read")` checks for that exact scope authority, if the authentication actually has it.
- Claim `app_roles: ["admin"]` only becomes `ROLE_ADMIN` **after** the mapper is written and runs successfully.

Never use rules like "having `SCOPE_profile` means `ROLE_ADMIN`" or treat every string from claims as a system permission.

## 3. Where is the mapper called in the Servlet OAuth2 Login flow?

~~~text
Browser
  |
  | GET /admin (no session yet)
  v
Spring Security -> Redirect to Authorization Server/IdP
  |
  | User logs in and consents to the application
  v
GET /login/oauth2/code/company?code=...&state=...
  |
  v
OAuth2/OIDC authentication provider
  |-- validate state, code flow, OIDC ID Token per framework mechanism
  |-- obtain OidcUser / OAuth2User and authorities
  v
GrantedAuthoritiesMapper
  |-- read chosen claim from ID Token or UserInfo
  |-- apply allowlist and convert app_roles => ROLE_*
  v
Authentication containing mapped authorities
  |
  v
SecurityContext / session
  |
  v
Authorization: hasRole("ADMIN"), @PreAuthorize(...), ...
~~~

**Timing:** the mapper is typically called **during authentication**, not re-invoked on every HTTP request. If roles change at the IdP while the user still holds a session, authorities attached to the authentication may **not yet be updated**. You need a policy for re-login, re-authentication, session revocation, or permission synchronization if immediate changes are required.

**Mapper input:** `Collection<? extends GrantedAuthority>`, not a JWT string and **without an `OAuth2AccessToken` available**. Accessible data depends on the authority type:

| Authority type | Reading data | Notes |
| --- | --- | --- |
| `OidcUserAuthority` | `getIdToken().getClaims()`; optionally `getUserInfo().getClaims()` | ID Token belongs to OIDC flow; UserInfo may not exist. |
| `OAuth2UserAuthority` | `getAttributes()` | Belongs to non-OIDC OAuth2 login or custom user services. |
| `SimpleGrantedAuthority` | `getAuthority()` | May hold `SCOPE_...` or other authorities from app-configured sources. |

**Trusted source:** with OIDC, Spring Security validates the token by issuer, audience, signature, and related rules in the standard flow. The mapper only **translates data already accepted by the authentication pipeline**. Never take claims from query parameters, arbitrary client-sent headers, or unverified JSON and turn them directly into permissions.

## 4. Designing a safe mapping policy

Before coding, define a **claim contract** with the IdP:

1. Claim name used as the basis for granting roles: e.g., `app_roles`.
2. Priority source: **ID Token** if the claim is present; use **UserInfo** only when allowed by the contract and the ID Token lacks the claim. Do not arbitrarily merge both sources with rules that could escalate privileges.
3. Data type: list of strings such as `["viewer","editor"]`; free-form strings or nested maps must not be blindly coerced into lists without a specification.
4. Allowed role set: `viewer`, `editor`, `admin`; other values are ignored or reject login per policy.
5. Normalization rules: only trim and match case-insensitively when permitted by the contract; never do fuzzy substring matching like checking if it contains `"admin"`.
6. Default rule: **missing/invalid claim => grant no business roles**.
7. Privileged rules: sensitive roles may require additional checks for tenant, internal registration, approvers, or separate authorization mechanisms.

**Do not** use directly:

~~~java
// Dangerous example: any claim could become ROLE_*.
new SimpleGrantedAuthority("ROLE_" + roleFromClaim);
~~~

If the ID Token/UserInfo contains `"super_admin"` outside the policy, the code above automatically creates `ROLE_SUPER_ADMIN`. Use an **allowlist** translating known input values to known authorities.

Never grant permissions just because `email` has the company suffix, `preferred_username` looks like an admin name, or `email_verified=true`. Those are identity/profile attributes, not substitutes for organizational authorization decisions.

## 5. Java 17+ and Spring Security 6 example: OIDC login + mapper

The following example runs on **Spring Boot 3.3.5** and **Java 17**. Pinned versions are chosen for reproducible syntax; production environments should use supported versions with security patches. The app needs a real OIDC Provider to complete login; **mapper unit tests require no provider connection**.

Structure:

~~~text
oauth-role-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── Application.java
    │   │   ├── AppAuthoritiesMapper.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/demo/AppAuthoritiesMapperTest.java
~~~

### 5.1. Maven dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>oauth-role-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 5.2. Mapper: map only the `app_roles` claim via an allowlist

**src/main/java/demo/AppAuthoritiesMapper.java**

~~~java
package demo;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;
import org.springframework.stereotype.Component;

@Component
public final class AppAuthoritiesMapper implements GrantedAuthoritiesMapper {

    @Override
    public Collection<? extends GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> incoming) {
        Set<GrantedAuthority> result = new LinkedHashSet<>();

        for (GrantedAuthority authority : incoming) {
            if (authority instanceof OidcUserAuthority oidc) {
                // Keep OIDC_USER and original identity data.
                result.add(oidc);

                Map<String, Object> claims = oidc.getIdToken().getClaims();

                // Only fall back to UserInfo if the ID Token does NOT have the claim.
                if (!claims.containsKey("app_roles")
                        && oidc.getUserInfo() != null) {
                    claims = oidc.getUserInfo().getClaims();
                }

                addApplicationRoles(claims, result);

            } else if (authority instanceof OAuth2UserAuthority oauth2) {
                result.add(oauth2); // Keep OAUTH2_USER.
                addApplicationRoles(oauth2.getAttributes(), result);

            } else if (authority.getAuthority() != null
                    && authority.getAuthority().startsWith("SCOPE_")) {
                // Keep scope authorities per demo policy,
                // do NOT automatically elevate scopes to ROLE_ADMIN.
                result.add(authority);
            }
        }

        return result;
    }

    private static void addApplicationRoles(
            Map<String, Object> claims,
            Set<GrantedAuthority> result) {
        Object raw = claims.get("app_roles");

        // Fail closed if the IdP does not issue a list of strings.
        if (!(raw instanceof Collection<?> roles)) {
            return;
        }

        for (Object item : roles) {
            if (!(item instanceof String role)) {
                continue;
            }

            String key = role.trim().toLowerCase(Locale.ROOT);

            switch (key) {
                case "viewer" ->
                    result.add(new SimpleGrantedAuthority("ROLE_VIEWER"));
                case "editor" ->
                    result.add(new SimpleGrantedAuthority("ROLE_EDITOR"));
                case "admin" ->
                    result.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                default -> {
                    // Do not create roles for unknown values.
                }
            }
        }
    }
}
~~~

Explanation of security decisions:

- Only read `app_roles` from authorities provided by the framework after login. The code never trusts roles self-declared by the browser.
- For OIDC, prioritize the claim in the ID Token; only fall back to UserInfo when the claim is **completely missing** from the ID Token. If the ID Token has the claim with a wrong type or unknown values, the code does not fall back to another source to "rescue" by granting permissions.
- For non-OIDC OAuth2 login, use `OAuth2UserAuthority.getAttributes()`, suitable when the provider supplies `app_roles` via fetched user data.
- Ignore mistyped claims and roles outside the allowlist.
- Use `LinkedHashSet` to avoid duplicate authorities.
- Keep identity authorities `OIDC_USER`/`OAUTH2_USER` and `SCOPE_` entries inserted by Spring Security; **do not** blindly copy existing `ROLE_*` entries from unaudited sources. If the app has other valid base authorities, extend the retention policy explicitly.
- The mapper only maps roles. Critical business policies still require per-resource authorization.

**Note:** `List` is imported in the example for convenience during further development even though it is not used directly in the mapper class; you can remove that import without affecting compilation.

### 5.3. Registering the mapper in Spring Security Servlet

**src/main/java/demo/SecurityConfiguration.java**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AppAuthoritiesMapper mapper) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/edit").hasAnyRole("EDITOR", "ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(info ->
                    info.userAuthoritiesMapper(mapper)
                )
            );

        // Keep default CSRF protection for session/cookies.
        return http.build();
    }
}
~~~

`.userAuthoritiesMapper(mapper)` is the key integration hook for `oauth2Login()`. Once OAuth2/OIDC login succeeds, the authority set returned by the mapper is placed into `Authentication`, which Spring Security then evaluates with `hasRole` / `hasAuthority`.

`hasRole("ADMIN")` requires `ROLE_ADMIN` under the default role prefix. **Do not** write `hasRole("ROLE_ADMIN")` while still using the default prefix, as that easily causes prefix configuration bugs. For non-role permissions like `INVOICE_APPROVE`, use `hasAuthority("INVOICE_APPROVE")` or a suitable `AuthorizationManager`.

**src/main/java/demo/DemoController.java**

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "Open /me, /edit or /admin");
    }

    @GetMapping("/me")
    Map<String, Object> me(Authentication authentication) {
        List<String> names = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "username", authentication.getName(),
            "authorities", names
        );
    }

    @GetMapping("/edit")
    Map<String, String> edit() {
        return Map.of("status", "editor-or-admin");
    }

    @GetMapping("/admin")
    Map<String, String> admin() {
        return Map.of("status", "admin");
    }
}
~~~

Only return **authority names** on `/me` to observe learning results; **never output the ID Token, access token, refresh token, or sensitive claims** to responses or logs. Production apps typically return only what the UI genuinely needs.

### 5.4. Connecting an OIDC Provider

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

**In the actual YAML file**, the Spring environment placeholder syntax must be `client-id: ${OIDC_CLIENT_ID}`, `client-secret: ${OIDC_CLIENT_SECRET}`, and `issuer-uri: ${OIDC_ISSUER_URI}`; these three values are read from environment variables. Do not hard-code real client secrets into the repository.

The IdP must have a valid redirect URI configured for the `company` registration, typically:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

Test logging in via `/oauth2/authorization/company`; the browser goes through the provider and returns to the callback after the authorization-code flow. To receive `ROLE_EDITOR` in the example, the IdP must actually emit the claim `app_roles: ["editor"]` in the **ID Token**, or in **UserInfo** when the ID Token omits the claim; the claim does not appear automatically just by declaring `scope: openid, profile, email`.

**Run the project with a valid configured OIDC Provider:**

~~~bash
mvn spring-boot:run
~~~

Expected results after logging in with `app_roles: ["editor"]`:

| Request | Expectation |
| --- | --- |
| `GET /` | 200, public. |
| `GET /me` when unauthenticated | Redirected to the login page per default flow. |
| `GET /me` authenticated | 200, authorities include `ROLE_EDITOR`; may include `OIDC_USER`, `SCOPE_...`. |
| `GET /edit` authenticated as editor | 200. |
| `GET /admin` authenticated as editor without `ROLE_ADMIN` | 403 Forbidden. |
| `GET /admin` authenticated as admin | 200 if the mapper actually produced `ROLE_ADMIN`. |

**Scope warning:** never implement state-changing endpoints with GET like `/edit`; the example returns status purely to observe authorization. Real write operations must use appropriate HTTP methods, be CSRF-protected when authenticated via session cookie, and enforce permissions and business checks.

## 6. Unit testing the mapper: no running IdP required

**src/test/java/demo/AppAuthoritiesMapperTest.java**

~~~java
package demo;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.user.OAuth2UserAuthority;

import static org.assertj.core.api.Assertions.assertThat;

class AppAuthoritiesMapperTest {

    private final AppAuthoritiesMapper mapper = new AppAuthoritiesMapper();

    private static Set<String> names(
            Collection<? extends GrantedAuthority> authorities) {
        return authorities.stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void mapsOidcIdTokenRolesAndKeepsScope() {
        var token = new OidcIdToken(
            "id-token-used-only-in-this-unit-test",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2026-01-01T01:00:00Z"),
            Map.of(
                "sub", "user-1",
                "app_roles", List.of("editor", "viewer", "unknown")
            )
        );

        var mapped = mapper.mapAuthorities(List.of(
            new OidcUserAuthority(token),
            new SimpleGrantedAuthority("SCOPE_email")
        ));

        assertThat(names(mapped))
            .contains("OIDC_USER", "SCOPE_email",
                      "ROLE_EDITOR", "ROLE_VIEWER")
            .doesNotContain("ROLE_ADMIN", "ROLE_UNKNOWN");
    }

    @Test
    void mapsNonOidcUserAttributesWithAllowlist() {
        var oauth2 = new OAuth2UserAuthority(Map.of(
            "id", "user-2",
            "app_roles", List.of(" admin ", "admin", "other")
        ));

        var mapped = mapper.mapAuthorities(List.of(oauth2));

        assertThat(names(mapped))
            .contains("OAUTH2_USER", "ROLE_ADMIN")
            .doesNotContain("ROLE_OTHER");
    }

    @Test
    void missingOrMalformedRolesDoNotElevateUser() {
        var noClaim = new OAuth2UserAuthority(Map.of(
            "id", "user-3",
            "email", "admin@example.test"
        ));
        var wrongType = new OAuth2UserAuthority(Map.of(
            "id", "user-4",
            "app_roles", "admin"
        ));
        var nonStrings = new OAuth2UserAuthority(Map.of(
            "id", "user-5",
            "app_roles", List.of(42, true)
        ));

        for (var authority : List.of(noClaim, wrongType, nonStrings)) {
            assertThat(names(mapper.mapAuthorities(List.of(authority))))
                .contains("OAUTH2_USER")
                .doesNotContain("ROLE_ADMIN", "ROLE_EDITOR", "ROLE_VIEWER");
        }
    }

    @Test
    void unsupportedRoleCannotCreateArbitraryAuthority() {
        var oauth2 = new OAuth2UserAuthority(Map.of(
            "id", "user-6",
            "app_roles", List.of("super_admin", "ROLE_ADMIN")
        ));

        assertThat(names(mapper.mapAuthorities(List.of(oauth2))))
            .doesNotContain("ROLE_SUPER_ADMIN", "ROLE_ADMIN");
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn test
~~~

**Expectation:** all 4 tests pass. This is the expected outcome when running the exact source above, not a log recorded from a verified execution environment.

Note that tests constructing `OidcIdToken` manually **only test the mapper**; they do not verify JWT signatures or a real OIDC flow. Token/issuer/audience validation belongs to integration tests and OAuth2 Login configuration with a trusted IdP. Avoid using such manually constructed token objects in production.

## 7. When claims are absent from ID Token or UserInfo

With some IdPs, roles exist only in the **Access Token** (e.g., `realm_access.roles`) or in a dedicated group/permission management API. `GrantedAuthoritiesMapper` is not directly given an `OAuth2AccessToken`, as it only receives a collection of authorities.

There are three design options:

1. **Prefer configuring the IdP to emit application claims into the ID Token/UserInfo**, if IdP policy permits and claims match the right audience/context.
2. **Customize `OAuth2UserService` / `OidcUserService`**, where `OAuth2UserRequest`/`OidcUserRequest` provides access token information. The service can call a trusted role endpoint using an appropriate token and then build a principal carrying verified authorities. Apply timeouts, error checks, minimal token scopes, and a fail-closed policy.
3. **Look up internal permissions from a database** by the stable identifier `issuer + sub` or linked user key; appropriate when permissions are determined by the application itself rather than the IdP.

**Do not** decode the Access Token as a JWT yourself and treat its contents as application permissions while skipping issuer, audience, signature, and intended-use validation. An access token may be opaque, may be issued for a different resource server, or may not have the JWT structure or claims you assumed.

If the IdP uses nested claims like `realm_access.roles`, write an extractor matching the schema, validate types at each nesting level, and grant permissions only via an allowlist. The mapper in Section 5 **intentionally understands only the `app_roles` schema** and does not guess every IdP's claim names.

## 8. `GrantedAuthoritiesMapper` vs. `JwtAuthenticationConverter`

This is a common point of confusion in Spring Security:

| Scenario | Authentication | Appropriate permission conversion point |
| --- | --- | --- |
| Servlet web app using `oauth2Login()` | `OAuth2AuthenticationToken` and `OAuth2User` / `OidcUser` | `GrantedAuthoritiesMapper` in `oauth2Login().userInfoEndpoint()`; or custom user service. |
| REST API using `oauth2ResourceServer().jwt()` | `JwtAuthenticationToken` | `JwtAuthenticationConverter` and `JwtGrantedAuthoritiesConverter` / custom converter. |
| API authenticating via opaque token introspection | Bearer token authentication with principal from introspection | Custom introspector/authority conversion depending on configuration. |
| OAuth2 Client calling downstream API | `OAuth2AuthorizedClient` / access token | Permissions are verified at the target resource server; UI roles do not automatically become API permissions. |

Therefore, if the mapper works in the web app but requests to the resource server still return 403, the mapper is not necessarily wrong: the resource server has its **own** bearer token verification and authorization decisions. Never pass roles from `/me` or from the browser as proof of API permissions.

## 9. `ROLE_`, `SCOPE_`, and `@PreAuthorize`

Roles/authorities are **strings** used by Spring Security in access decisions; `SimpleGrantedAuthority` is just a wrapper holding that string.

Example:

~~~java
// If Authentication has ROLE_EDITOR:
.requestMatchers("/edit").hasRole("EDITOR")

// Check exact authority without adding ROLE_:
.requestMatchers("/audit").hasAuthority("AUDIT_READ")
~~~

This is an **illustrative DSL configuration snippet**, not a standalone Java file. `hasRole("EDITOR")` matches `ROLE_EDITOR` with the default prefix. Meanwhile `hasAuthority("AUDIT_READ")` matches `AUDIT_READ` verbatim.

If `@EnableMethodSecurity` is enabled, a service can enforce:

~~~java
@PreAuthorize("hasRole('EDITOR') or hasRole('ADMIN')")
public void updateArticle(long articleId, String text) {
    // Perform additional permission checks on articleId in the business layer.
}
~~~

This is also a **method illustration inside a service that imports `PreAuthorize`**, not a standalone runnable class. In a multi-tenant system, you must also evaluate which tenant `articleId` belongs to and whether the caller can edit that article; a role alone is not enough.

Avoid creating roles with the exact same names as scopes and conflating them implicitly. A policy can use `ROLE_EDITOR` for UI roles, `ARTICLE_WRITE` for business operations, and `SCOPE_articles.write` for client API-calling permissions; the three do not have to be synonymous.

## 10. Common errors and how to diagnose them

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Login succeeds, `/admin` returns 403 | Mapper did not create `ROLE_ADMIN`; claim missing/wrong source/wrong type; user truly lacks role. | Inspect verified claim schema, mapper output, and `hasRole` policy. |
| Has `SCOPE_profile` but fails `hasRole("ADMIN")` | Scope differs from role. | Map roles per explicit policy; never elevate scopes to admin. |
| Token has `realm_access.roles` but mapper does not see it | Claim exists **only in Access Token**, not in ID Token/UserInfo read by mapper. | Configure IdP to include appropriate claim or use custom user service/role lookup. |
| Claim `"ADMIN"` present but fails check | Claim name differs from `app_roles`, data is not an array, or mapping skipped it. | Identify exact claim contract and verify with test cases. |
| UserInfo lacks role while ID Token has role | Mapper policy prioritizes ID Token. | Inspect the right source; avoid overwriting with a less trusted source. |
| `hasRole("ROLE_ADMIN")` fails to match | `ROLE_` prefix prepended additionally per default matcher. | Write `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")`. |
| User's role changed at IdP but web app keeps old role | Authorities are mapped at login and may be stored in the session. | Establish refresh/re-login/session revocation policies. |
| Mapper roles are right, yet bearer token API still returns 403 | Resource Server uses a separate converter. | Check JWT converter/audience/scopes and API-side policy. |
| User from another tenant still has admin role | Global role not bound to resource/tenant. | Add per-resource/tenant authorization instead of relying only on `ROLE_ADMIN`. |
| Opening `/oauth2/authorization/company` does not reach IdP | Incorrect client registration, issuer metadata, redirect URI, or environment. | Check provider config, client ID, secret, and callback URL. |

When debugging, log **authority names and role counts** in a controlled test environment; never log raw ID Tokens, access tokens, refresh tokens, client secrets, or full personal information. A 403 from authorization differs from an authentication/OIDC validation failure; examine exceptions and security filter logs at an appropriate level.

## 11. Safe implementation workflow in real projects

1. **Define subjects and permission requirements:** which roles may perform which actions, what scopes signify, and which permissions must be checked per resource/tenant.
2. **Identify issuer, audience, and login type:** OIDC/OAuth2 web login, JWT resource server, or service-to-service.
3. **Align on the claim schema** with the IdP or internal authorization source: name, type, where it is issued, effective timing, and revocation responsibility.
4. **Map with an allowlist and fail closed:** never construct undefined authorities; handle nulls, missing/mistyped claims, unknown roles, and duplicates.
5. **Integrate into the right filter chain** and confirm which endpoints use `hasRole`, `hasAuthority`, `@PreAuthorize`, or object-level permission checks.
6. **Test both happy and failure paths:** OIDC, non-OIDC OAuth2, viewer/editor/admin, unknown role, missing claim, malformed claim, role changes, and cross-tenant cases.
7. **Verify against a real provider** after unit tests pass: confirm the claim is actually in the ID Token/UserInfo and the mapper is invoked in the right login flow.
8. **Control authority lifecycle:** logout, session timeout, role revocation, internal sync, and re-authentication when permissions change.
9. **Keep other protections intact:** web app CSRF for session/cookies, HTTPS, session fixation protection, secret management, safe logging, and service-layer authorization.

## 12. Self-check

**1.** Does `email_verified: true` automatically create `ROLE_USER`?  
**Answer:** No. That claim describes email verification status; map it to an authority only under an explicit app policy, and normally do not use it as proof for granting permissions.

**2.** Does `app_roles: ["admin"]` in the ID Token make the user an admin on every resource server?  
**Answer:** No. The mapper creates authorities for **the web app's authentication**. Resource servers validate their own bearer tokens, audiences, and converters.

**3.** Why does the code use an allowlist instead of concatenating `"ROLE_" + role`?  
**Answer:** To grant only defined application permissions, preventing unexpected authorities from invalid claims or schema changes.

**4.** Can the mapper call an API with an access token directly inside `mapAuthorities`?  
**Answer:** The signature has no access token. If you need tokens and network lookups, use a custom `OAuth2UserService`/`OidcUserService` or another suitable permission-lookup architecture.

**5.** Does having `ROLE_EDITOR` mean being allowed to edit every document?  
**Answer:** No. For specific documents, you still need checks for owner, tenant, status, and per-resource policies.

**6.** If the IdP updates roles while a user is logged in, do permissions in the session change immediately?  
**Answer:** Usually they do not change automatically until authentication is rebuilt; you need refresh/re-login/revocation policies or dynamic permission checks.

---

**Remember:** `GrantedAuthoritiesMapper` is the bridge between **claims/authorities after OAuth2–OIDC login** and **`GrantedAuthority` in a Spring Security Servlet application**. Clearly define claim sources, map only from an allowlist, distinguish `ROLE_` from `SCOPE_`, default to no privilege elevation when claims are missing or invalid, and always enforce resource-context authorization.