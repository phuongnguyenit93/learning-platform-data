# Inspecting `ROLE_`, Authorities, and Scopes When Decisions Do Not Match Expectations

> **Topic:** Observing and debugging **authentication/authorization** decisions in Spring Security 6.x on the Servlet stack, with Java 17+ and Spring Boot 3.x. The focus is on inspecting **actual authorities inside `Authentication`**, matching `hasRole`/`hasAuthority`, understanding `ROLE_` and `SCOPE_` prefixes, analyzing JWT/OAuth2 scopes, CSRF, filter chains, and method security. The runnable example uses HTTP Basic to isolate the issue; the JWT section is a separate integration guide and does not assume `UserDetailsService` is called for every token.

## 1. Symptom: Logged In, Yet Still Getting 403

An API has the rule:

```java
.requestMatchers("/api/admin").hasRole("ADMIN")
```

The client logs in successfully yet receives **403 Forbidden**. The developer opens the database, sees `role = ADMIN`, and concludes "Spring Security is broken." In reality, by default **`hasRole("ADMIN")` looks for authority `ROLE_ADMIN`**, not the string `ADMIN`. If the mapper creates `SimpleGrantedAuthority("ADMIN")`, authentication can succeed while authorization is denied.

Another case: a JWT carries `"scope": "reports.read"`, yet the endpoint requires `hasAuthority("reports.read")`. Spring Security Resource Server typically converts valid scopes into **`SCOPE_reports.read`** authorities. When the rule checks a mismatched string, the request receives 403 even though the token is valid.

Break the problem into separate questions:

1. **Is the request authenticated?** Does a real principal exist and is it not anonymous? With HTTP Basic/Bearer, invalid credentials typically result in 401; form login may redirect.
2. **Which `SecurityFilterChain` did the request pass through?** Another chain, a different `securityMatcher`, or an earlier broad rule may be deciding instead of the rule you think.
3. **What exact strings does `Authentication.getAuthorities()` currently hold?** Do not infer from a role column, JSON claim, or what the frontend says.
4. **What string does authorization check?** `hasRole`, `hasAuthority`, `@PreAuthorize`, scopes, role hierarchy, a custom `AuthorizationManager`, or ownership conditions?
5. **Did another mechanism deny before or after authorization?** CSRF, account state, method security, ACLs, tenant/owner checks, or exception handling?

**Learning objective:** debug from evidence at the right layer; never "fix a 403" by granting higher privileges or disabling protections.

## 2. Three Easily Confused Concepts: Role, Authority, and OAuth Scope

### 2.1. `GrantedAuthority` Is the Common Foundation

In Spring Security, `Authentication` holds a collection of `GrantedAuthority`. Most common configurations represent permissions as strings:

```java
new SimpleGrantedAuthority("ROLE_ADMIN");
new SimpleGrantedAuthority("SCOPE_reports.read");
new SimpleGrantedAuthority("invoice:approve");
```

These are **illustrative values** from code that imports `org.springframework.security.core.authority.SimpleGrantedAuthority`, not a standalone Java program. The framework does not require every authority to start with `ROLE_`: you can use `"invoice:approve"`, `"SCOPE_reports.read"`, or another business format, as long as the **producer** (authority source) and **consumer** (authorization rule) agree on the same convention.

**Key rule:** `hasAuthority("X")` checks whether an authority equals **the exact string `"X"`**. Case, dots, colons, and prefixes all matter. Some advanced setups (such as a role hierarchy) can expand the effective authority set, but you cannot assume two different strings are equivalent by default.

### 2.2. `hasRole` Prepends the Default Prefix

By default, the role prefix is `ROLE_`:

| Value in `Authentication` | Rule | Typical Result |
| --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | **Allowed** |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | **Allowed** |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | **Denied** |
| `ADMIN` | `hasRole("ADMIN")` | **Denied** |
| `ADMIN` | `hasAuthority("ADMIN")` | **Allowed** |
| `ROLE_USER` | `hasRole("ADMIN")` | **Denied** |
| `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | **Allowed** |
| `SCOPE_reports.read` | `hasRole("reports.read")` | **Denied** |

`hasRole("ADMIN")` is shorthand for requesting a role by convention, whereas `hasAuthority("ROLE_ADMIN")` states the exact required string. If an app customizes the default role prefix (for example via `GrantedAuthorityDefaults` or the corresponding API at certain layers), verify the actual configuration: never assume every `hasRole` behaves identically across every version and setup.

**Do not pass `hasRole("ROLE_ADMIN")` out of habit:** in the HTTP DSL, `hasRole` expects a **role name without the prefix**; some APIs detect and reject values that already carry `ROLE_`. Write either `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` to avoid confusion.

### 2.3. `roles(...)` and `authorities(...)` When Creating Users

Spring Security's `UserDetails` builder offers two ways to express permissions:

```java
// Example in code using the UserDetails builder:
User.withUsername("alice")
    .password(storedHash)
    .roles("ADMIN")
    .build();  // grants authority "ROLE_ADMIN"

User.withUsername("bob")
    .password(storedHash)
    .authorities("ROLE_ADMIN", "SCOPE_reports.read")
    .build();  // keeps the declared strings as-is
```

`.roles("ADMIN")` **automatically prepends `ROLE_`**; `.authorities("ROLE_ADMIN")` preserves strings unchanged. Do not pass `"ROLE_ADMIN"` into `.roles(...)` expecting the framework to "smartly" avoid duplicating the prefix. Do not re-hash `storedHash` while loading `UserDetails`; the password encoder is used when creating hashes and verifying passwords in the provider, and does not determine authorities.

The source of authorities can be database mappings, LDAP, a custom `UserDetailsService`, OAuth2/OIDC authorities, a JWT claims converter, or an internal service. **The first thing to check is the final output of that source inside `Authentication`**, not merely the raw input value.

### 2.4. Scopes Are Permissions Represented as Authorities in Resource Server

An OAuth2 *scope* expresses the permissions granted to a token. With Spring Security JWT Resource Server and the default `JwtGrantedAuthoritiesConverter`, the familiar `"scope"` or `"scp"` claim is converted into authorities prefixed with **`SCOPE_`**. For example:

```json
{
  "sub": "user-123",
  "scope": "reports.read reports.write"
}
```

In a typical JWT setup, this produces two authorities, `SCOPE_reports.read` and `SCOPE_reports.write`—**not** `reports.read`, `ROLE_reports.read`, or a single authority containing the space-separated string.

Important caveats:

- The token must be **verified** (signature or introspection, issuer, expiration, audience per configured requirements) before trusting claims. Never decode an unverified JWT and grant authorities directly from its JSON.
- `"scope"` and `"scp"` are two common alternative claim names, not a rule followed by every provider. Claims such as `permissions`, `roles`, `realm_access.roles`, or `resource_access` are **not automatically** converted to `ROLE_` or `SCOPE_` by default.
- `JwtGrantedAuthoritiesConverter` supports customizing the claim name and authority prefix when a token provider uses a different convention. Do not prepend `SCOPE_` a second time if the converter already adds it.
- Scopes describe the **token's** permissions; they do not prove the user owns a record or belongs to the requested tenant. Object/tenant access still requires data-level authorization policies.

## 3. Diagnosing HTTP 401, 403, 404, and Redirects Before Inspecting Roles

| Observation | Layer to Check First | Example Causes |
| --- | --- | --- |
| **401** on Basic GET API | Authentication | No Basic credentials sent, wrong password, user does not exist, provider rejects credentials. |
| **401** on JWT API | Bearer token validation | Expired token, bad signature/issuer/audience, missing Bearer token, decoder/introspector failure. |
| **403** on GET after login | Authorization | Missing `ROLE_...`, `SCOPE_...`, exact authority, or owner/tenant permission. |
| **403** on POST/PATCH/DELETE | **CSRF first**, then authorization | Missing/invalid CSRF token; or valid token but missing authority. |
| **404** for a known ID | Object-level policy or routing | Query includes an owner/tenant predicate intentionally hiding out-of-scope resources; or route/item truly absent. |
| **302** to login | Form-login authentication entry point | Interactive login configured instead of Basic/Bearer API handling. |
| Unexpected **200** | Chain/matcher/test setup | Overly broad `permitAll`, request hit another chain, test disabled filters. |

**Do not adjust roles before distinguishing authentication from authorization.** In Spring Security, unauthenticated requests can be handled by an `AuthenticationEntryPoint` (401 or redirect), while authenticated users lacking permissions are normally handled by an `AccessDeniedHandler` resulting in 403. With CSRF, the filter can reject a request before any controller or service runs.

### 3.1. Anonymous Is Not a Real Logged-In Account

Spring Security can place an `AnonymousAuthenticationToken` in `SecurityContext` for anonymous requests. Therefore, checking only `authentication != null` or `authentication.isAuthenticated()` **does not always prove the user actually logged in**, because an anonymous token can report itself as authenticated. Use Spring Security's `AuthorizationManager`/`authenticated()` or `AuthenticationTrustResolver` when distinguishing them; never treat an anonymous token's `getName()` as a real user ID.

### 3.2. `ROLE_` and `SCOPE_` Are Not Equivalent

A user with `ROLE_ADMIN` **does not automatically have** `SCOPE_reports.read`. A JWT with `SCOPE_reports.read` **does not automatically have** `ROLE_ADMIN`. If business rules say "admins can read all reports," **design the policy explicitly**—for instance combining `hasRole("ADMIN") OR hasAuthority("SCOPE_reports.read")` when business-appropriate—rather than automatically granting every scope just because a role contains the word ADMIN.

**Never adopt "fixes to clear 403"** such as `permitAll()`, `.csrf(disable)`, or giving `ROLE_ADMIN` to every account. That widens privileges and can turn a configuration bug into a security vulnerability.

## 4. First Debugging Step: Inspect Effective Authorities

The most important value is the `Authentication` **actively present on the denied request**, after authentication and authority conversion. On an authenticated endpoint, code can inspect:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String username = authentication.getName();
    List<String> authorities = authentication.getAuthorities()
        .stream()
        .map(GrantedAuthority::getAuthority)
        .sorted()
        .toList();
    // Use only in protected debug/test environments.
}
```

This snippet is an **illustrative sample** requiring imports for `Authentication`, `SecurityContextHolder`, `GrantedAuthority`, `java.util.List`, and an environment with a `SecurityContext`. Never output `authentication.getCredentials()`, password hashes, raw JWTs, session cookies, or arbitrary full principals. Restrict logging of principals and authorities in production according to data-protection policies.

### 4.1. Safe Observation in the Hands-On Exercise

In the runnable example in section 5, an authenticated `/api/me` endpoint returns only `username` and sorted authority strings for deterministic tests. **This is a demo endpoint**, not recommended to leave enabled unconditionally in production. If real diagnostics are needed, restrict to admin/support permissions, redact, audit, and disable after resolution.

Suppose the response is:

```json
{
  "username": "analyst",
  "authorities": [
    "ROLE_ANALYST",
    "SCOPE_reports.read",
    "SCOPE_reports.write"
  ]
}
```

Compare character-by-character against rules:

- `hasRole("ADMIN")` requires `ROLE_ADMIN` → absent → 403.
- `hasAuthority("SCOPE_reports.read")` → present → allowed.
- `hasAuthority("reports.read")` → **absent** → 403.
- `hasAuthority("ROLE_ANALYST")` → present → allowed.
- `hasRole("ANALYST")` → present → allowed under the default prefix.

**Note:** the UI might display "Analyst" or "Admin," yet that does not determine backend authorities. Never rely on menu labels, client-set cookies, or unverified role fields in JSON.

## 5. Runnable Java 17+ Example: Finding Role and Scope Bugs with HTTP Basic

This example uses Spring Boot 3.x with two accounts and directly assigned role/scope-like authorities:

- `analyst` / `analyst123`: `ROLE_ANALYST`, `SCOPE_reports.read`, `SCOPE_reports.write`.
- `admin` / `admin123`: `ROLE_ADMIN`, **without report scopes**.

The goal is to **demonstrate authority matching**, not to mock JWT verification. In real applications, `SCOPE_...` usually comes from a Bearer token converter, yet `hasAuthority` evaluates the exact same strings regardless of which authentication source produced them.

### 5.1. Gradle Structure

`settings.gradle`:

```groovy
rootProject.name = 'authority-diagnostics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot **3.3.5** is an **illustrative pinned version**, not the latest release. Spring Boot manages compatible Spring Security and test artifacts together. You can run `gradle test` with a compatible Gradle installation or Gradle Wrapper. JDK 17+ and access to configured dependency repositories are required to run the demo.

### 5.2. Full Application Code

Create `src/main/java/demo/diagnostics/AuthorityDiagnosticsApplication.java`:

```java
package demo.diagnostics;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthorityDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorityDiagnosticsApplication.class, args);
    }
}

record IdentityView(String username, List<String> authorities) {}

@RestController
class DemoEndpoints {
    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    IdentityView me(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new IdentityView(authentication.getName(), authorities);
    }

    @GetMapping("/api/admin")
    String roleAdmin() {
        return "admin-role-ok";
    }

    @GetMapping("/api/admin/exact")
    String exactAdmin() {
        return "admin-authority-ok";
    }

    @GetMapping("/api/admin/strict")
    String strictAdmin() {
        return "plain-admin-ok";
    }

    @GetMapping("/api/reports")
    String reports() {
        return "reports-read";
    }

    @PostMapping("/api/reports/export")
    @ResponseStatus(HttpStatus.ACCEPTED)
    String exportReports() {
        return "export-request-accepted";
    }
}

@Configuration
class DemoSecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("analyst")
                .password(encoder.encode("analyst123"))
                .authorities(
                    "ROLE_ANALYST",
                    "SCOPE_reports.read",
                    "SCOPE_reports.write"
                )
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/reports/export")
                    .hasAuthority("SCOPE_reports.write")
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers("/api/admin/exact")
                    .hasAuthority("ROLE_ADMIN")
                .requestMatchers("/api/admin/strict")
                    .hasAuthority("ADMIN")
                .requestMatchers("/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
```

**Observation:** `DemoSecurityConfiguration` grants `ROLE_ADMIN` to `admin` via `.roles("ADMIN")`; the `/api/admin/strict` endpoint intentionally requires **`hasAuthority("ADMIN")`** to illustrate a buggy rule when the author meant to check role `ADMIN`. Even the real admin gets 403 on the strict endpoint because **no bare `ADMIN` authority exists**. By contrast, `/api/admin` using `hasRole("ADMIN")` and `/api/admin/exact` using `hasAuthority("ROLE_ADMIN")` both let `admin` through.

The `/api/reports` endpoint checks `SCOPE_reports.read` and the export POST checks `SCOPE_reports.write`: `analyst` is permitted, while `admin` does not automatically possess those scopes. The POST rule precedes the GET rule. Default Servlet CSRF remains enabled; HTTP Basic is used to demonstrate 401/403 without form-login redirects.

`@RestController` and `DemoSecurityConfiguration` are package-private classes in the same file as the public application class, which is valid Java. In production, never keep hardcoded demo accounts or expose unrestricted authority-inspection endpoints.

### 5.3. Concrete Results When Running with curl

Start from the project directory:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`; if no Gradle Wrapper is present, use `gradle bootRun` with a compatible Gradle 8.x version. By default the demo listens on `localhost:8080`.

The following Bash commands print **only the HTTP status**, independent of response body:

```bash
# 1. Public
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/public

# 2. Protected without credentials
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me

# 3. Wrong password
curl -s -o /dev/null -w '%{http_code}\n' \
  -u analyst:wrong http://localhost:8080/api/me

# 4. Valid ADMIN role
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin

# 5. Exact authority ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin/exact

# 6. Intentionally mismatched "ADMIN" vs "ROLE_ADMIN"
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/admin/strict

# 7. Analyst missing ROLE_ADMIN
curl -s -o /dev/null -w '%{http_code}\n' \
  -u analyst:analyst123 http://localhost:8080/api/admin

# 8. Analyst has scope-like authority to read reports
curl -s -o /dev/null -w '%{http_code}\n' \
  -u analyst:analyst123 http://localhost:8080/api/reports

# 9. Admin has role but lacks reports.read scope
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin123 http://localhost:8080/api/reports
```

Each command prints one status line; expected results in order:

```text
200
401
401
200
200
403
403
200
403
```

To inspect `analyst`'s actual authorities in the demo:

```bash
curl -s -u analyst:analyst123 \
  http://localhost:8080/api/me
```

Expected JSON response (Spring MVC/Jackson may omit whitespace):

```json
{"username":"analyst","authorities":["ROLE_ANALYST","SCOPE_reports.read","SCOPE_reports.write"]}
```

These are **post-authentication values**, sufficient to explain all evaluated rules without guessing from a roles table. For `admin`, the authorities list contains only `ROLE_ADMIN`.

**Note:** `curl` with HTTP Basic over plain HTTP should only be used on localhost for learning. Production must use TLS/HTTPS and proper credential management. For POST with default CSRF enabled, sending `-u` alone will not yield 202; use the MockMvc tests in the next section to supply a valid token or build a complete client CSRF flow.

## 6. Testing Precisely with `spring-security-test`

Create `src/test/java/demo/diagnostics/AuthorityDiagnosticsTest.java`. Tests use the full application context, real filter chain, and in-memory user service; do not mock the authentication provider in cases that verify password authentication.

```java
package demo.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorityDiagnosticsTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousOnProtectedEndpointGets401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicPasswordGets401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("analyst", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualAuthoritiesAppearInAuthenticatedPrincipal()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username")
                .value("analyst"))
            .andExpect(jsonPath("$.authorities",
                hasItems(
                    "ROLE_ANALYST",
                    "SCOPE_reports.read",
                    "SCOPE_reports.write"
                )));
    }

    @Test
    void hasRoleAdminPassesWhenUserHasRoleAdmin()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-role-ok"));
    }

    @Test
    void exactRoleAuthorityAlsoPasses() throws Exception {
        mvc.perform(get("/api/admin/exact")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk());
    }

    @Test
    void exactPlainAdminIsDifferentFromRoleAdmin()
            throws Exception {
        mvc.perform(get("/api/admin/strict")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystWithoutRoleAdminIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystWithReadScopeAuthorityIsAllowed()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports-read"));
    }

    @Test
    void adminRoleDoesNotGrantMissingReportScope()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingCsrfRejectsWriteEvenWithScope()
            throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("analyst", "analyst123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndWriteAuthorityPermitExport()
            throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("analyst", "analyst123"))
                .with(csrf()))
            .andExpect(status().isAccepted())
            .andExpect(content().string("export-request-accepted"));
    }

    @Test
    void validCsrfDoesNotGrantMissingWriteScope()
            throws Exception {
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("admin", "admin123"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void withMockUserRoleCreatesRoleAdmin() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void withMockUserExactAuthorityDoesNotSatisfyHasRole()
            throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void exactScopeAuthoritySatisfiesReportRule() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "reports.read")
    void missingScopePrefixFailsExactAuthorityCheck()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }
}
```

With `@WithMockUser`, Spring Security Test **injects a fake principal** into `SecurityContext` without checking passwords. Therefore `WithMockUser` tests only verify behavior for **simulated** authorities; the `httpBasic(...)` cases exercise the filter/provider/encoder to verify real credentials. Never use `@WithMockUser` as proof that a JWT was verified or that an account exists in the database.

**Regarding POST:** the first test gets 403 because no CSRF token is present under the demo configuration. The second adds `.with(csrf())`, and since `analyst` has `SCOPE_reports.write`, it returns 202. The third test **has valid CSRF yet lacks the scope**, so 403 is an authorization error, not a CSRF error. This side-by-side comparison pinpoints the exact cause.

### 6.1. Running the Tests

Using Gradle Wrapper in the project directory:

```bash
./gradlew test
```

Windows:

```bat
gradlew.bat test
```

Run only this suite:

```bash
./gradlew test --tests demo.diagnostics.AuthorityDiagnosticsTest
```

Tests pass when all assertions succeed; do not predict exact Gradle stdout because it depends on Gradle version, environment, and logging. You can **intentionally** change the `/api/reports` rule to `hasAuthority("reports.read")` in a dev copy and re-run the tests: the `SCOPE_reports.read` cases will fail, proving the suite catches prefix bugs.

## 7. Diagnostics Specific to JWT/OAuth2 Resource Server

The section 5 example uses Basic authentication to isolate role/authority behavior easily. With a JWT Resource Server, the path differs:

```text
Authorization: Bearer <JWT>
       |
       v
BearerTokenAuthenticationFilter
       |
       v
JwtAuthenticationProvider / JwtDecoder
       |  signature, issuer, expiry, audience per configuration
       v
JwtAuthenticationToken
       |  scope/scp claim -> JwtGrantedAuthoritiesConverter
       v
Authentication.getAuthorities() (e.g. SCOPE_reports.read)
       |
       v
AuthorizationFilter / method security -> 200 or 403
```

Do not expect `UserDetailsService.loadUserByUsername` to run automatically on every JWT request; a Resource Server normally authenticates tokens via a decoder/provider. Also avoid reading `jwt.getClaimAsString("role")` directly in a controller to bypass authorization rules without verifying claims and policies.

### 7.1. From Claims to Authority Strings

Example of an already-verified JWT:

```json
{
  "sub": "user-123",
  "scope": "reports.read reports.write",
  "roles": ["ADMIN"],
  "permissions": ["invoice:approve"]
}
```

With the default scopes converter, Spring Security Resource Server typically grants:

```text
SCOPE_reports.read
SCOPE_reports.write
```

`roles: ["ADMIN"]` and `permissions: ["invoice:approve"]` **do not automatically become** `ROLE_ADMIN` or authority `invoice:approve` unless an appropriate converter is configured. If an endpoint requires `hasRole("ADMIN")`, a token carrying only report scopes will still receive 403, and that may be **by design**, not a login failure.

### 7.2. Customizing the Converter When the Provider Uses Another Claim

A provider might use a `"permissions"` claim containing strings like `"reports.read"` instead of `"scope"`. When using Spring Security Resource Server with the `spring-boot-starter-oauth2-resource-server` dependency, you can map it as follows:

```java
// Illustrative integration snippet for JWT Resource Server config;
// DO NOT copy verbatim into the HTTP Basic demo above.

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();

    permissions.setAuthoritiesClaimName("permissions");
    permissions.setAuthorityPrefix("PERM_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(permissions);
    return converter;
}

@Bean
SecurityFilterChain jwtChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/jwt-api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/jwt-api/reports")
                .hasAuthority("PERM_reports.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter())
            )
        );
    return http.build();
}
```

This requires imports for `@Bean`, `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, `HttpSecurity`, `SecurityFilterChain`, and valid decoder configuration (such as trusted issuer/JWK set and audience validation as needed). This is a **directional snippet**, not a standalone runnable sample: it omits issuer/decoder config, routing with other chains, and real tokens. When integrating into an app with an existing Basic chain, design `@Order`/`securityMatcher` so the wrong chain does not intercept requests.

If you want `"ROLE_ADMIN"` authorities from a roles claim, you need a dedicated converter that enforces the `ROLE_` prefix, handles claim formats, and intentionally merges with scope authorities. Never blindly combine unverified roles, scopes, or permissions from an untrusted identity source.

**Important:** `JwtGrantedAuthoritiesConverter.setAuthoritiesClaimName("permissions")` points to a single claim; it **does not automatically merge** both `scope` and `permissions`. If you need both sources, build a tested composite converter or use appropriate delegation APIs.

### 7.3. `jwt()` in MockMvc Tests Does Not Test Signatures

Spring Security Test provides `.with(jwt())` to mock a JWT principal and authorities for authorization tests. It **does not prove** that production tokens are decoded properly, signed validly, or have claims mapped properly from a real issuer. To verify `JwtDecoder`, issuer/audience, expiry, and the real converter, write dedicated tests with the configured decoder/config or integration tests using properly generated/controlled HTTP Bearer tokens.

Example fragment (only for tests with the Resource Server module and matching imports):

```java
mvc.perform(get("/jwt-api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("PERM_reports.read")
        )))
    .andExpect(status().isOk());
```

In this fragment, `jwt()` sets authorities directly and therefore **skips whether the `permissions` claim is converted into the expected authority by your converter**. To test the converter, pass a JWT fixture through the converter itself or run the real token path and assert `Authentication.getAuthorities()`. Avoid picking fake authorities in tests that unintentionally hide mapping bugs.

### 7.4. Checklist for Debugging Missing-Scope Tokens

Dedicated checklist:

1. Is the response 401 or 403? **401** usually means the token was rejected during authentication; **403** post-authentication means missing authority/policy.
2. Were the token's signature, issuer, audience, and expiry validated?
3. Inspect the actual claim name and type (`scope` string, `scp` array, `permissions` list, nested roles).
4. Which converter is wired into JWT authentication? Does it use the right claim name and prefix?
5. What is `Authentication.getAuthorities()` in the end? Does it contain `SCOPE_reports.read` or `PERM_reports.read`?
6. Does the rule check `hasAuthority("SCOPE_reports.read")`, `hasRole("ADMIN")`, or another permission?
7. Are multiple filter chains or resource servers configured for different routes?
8. Even when the scope is present, is permission sufficient for **owner/tenant**, ACL, or method security? If not, 403/404 may still be right.

Never paste raw JWTs, cookies, or passwords into chats or logs when debugging. You can inspect claims in a safe environment with redacted data, and never trust an unverified payload.

## 8. When Logs Say "Access Denied" Without Making the Rule Clear

### 8.1. Enabling Security Logging Temporarily in Dev/Test

You can add configuration **only in a debug/test profile**:

```properties
logging.level.org.springframework.security=TRACE
```

For large apps, pick narrower loggers and drop back to DEBUG once you have enough detail. TRACE logs help observe filter chains, authentication, and authorization decisions, yet **exact wording varies by version**, and security logs can contain sensitive information. Never leave it enabled indefinitely in production; restrict log read access and retention, and never log tokens, passwords, or raw HTTP Authorization headers. Do not assume every TRACE entry prints the exact denied `GrantedAuthority` or expression; combine logging with diagnostic tests.

### 8.2. Following the Right Evaluation Chain

When getting 403, trace from outside in:

```text
Request URL + HTTP method
  |
  v
SecurityFilterChain matching?
  |  - securityMatcher, @Order, other filter chains
  v
Authentication type and principal?
  |  - anonymous, Basic, session, JWT, oauth2Login
  v
Authentication.getAuthorities()?
  |  - ROLE_..., SCOPE_..., exact business permissions
  v
Authorization rules?
  |  - requestMatchers, hasRole, hasAuthority, order
  v
Other checks?
  |  - CSRF filter, @PreAuthorize, @PostAuthorize
  |  - owner / tenant / ACL in service or repository
  v
Controller response / exception handler
```

**On matcher order:** inside `authorizeHttpRequests`, rules are evaluated in declaration order, so a broad rule placed before a specific rule can intercept the request. Wrong-intent example:

```java
// Wrong if you want /api/admin/** to have a stricter policy:
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Because `/api/**` is evaluated first and matches, the later admin policy may never run. Place specific rules before general rules. With multiple chains, `securityMatcher` decides which chain applies **before** any `requestMatchers` inside that chain are evaluated. Editing a rule in a chain the request never enters will not change the outcome.

### 8.3. Method Security Can Deny After HTTP Rules Pass

An endpoint has `.anyRequest().authenticated()`, yet the called service method has:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(Long invoiceId) {
    // Business logic
}
```

When `@EnableMethodSecurity` is enabled and the call passes through the Spring proxy, the method can deny a user lacking the authority **even though the HTTP rule permitted it**. The snippet above illustrates a method on a Spring bean importing `@PreAuthorize`, **not a standalone Java program**.

When debugging, check:

- Does the app have `@EnableMethodSecurity` and is the call going through the bean proxy?
- Do the principal's authorities include the exact string `invoice:approve`?
- Is there a custom `PermissionEvaluator`, role hierarchy, `@PostAuthorize`, or composite annotation?
- A `@WebMvcTest` that mocks the service can bypass real method security; write an integration test with the real service bean.
- Self-invocation within the same object can bypass the proxy; this can cause the policy **not to run at all**, which is worse than a 403. Structure bean calls to go through the proxy properly.

### 8.4. Custom Role Prefixes and Role Hierarchies

`GrantedAuthorityDefaults` can change the role prefix for components that honor it. If the system customized it, verify the **effective configuration** for both request authorization and method authorization, especially after upgrading Spring Security. Do not assume from one bean that every API shares the same prefix.

A role hierarchy (e.g., admin implying certain user permissions) can satisfy rules via **reachable authorities**, even when you only see the base authorities in `Authentication`. Thus, when outcomes differ from the table in section 2, check whether a custom `RoleHierarchy`, `AuthorizationManager`, method interceptor, or trust resolver is registered. Write tests for inherited roles rather than assuming "ROLE_ADMIN includes every scope."

## 9. Mistakes That Easily Cause 403 or Break Security

### 9.1. Accepting Roles from the Client Request to Clear Errors

**Never** accept `"role": "ADMIN"` or `"scope": "reports.write"` from a login/request body and convert it straight into a `GrantedAuthority`. Authorities must come from a trusted server-side source or verified claims accepted by policy. Otherwise, attackers grant themselves privileges.

### 9.2. Mismatching Prefixes

`hasAuthority("SCOPE_read")` does not match `SCOPE_reports.read`. `hasRole("ADMIN")` does not match bare `ADMIN` under default conventions. Build a clear producer/consumer mapping table:

| Source | Actual Value | Appropriate Rule |
| --- | --- | --- |
| `.roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")`. |
| `.authorities("ADMIN")` | `ADMIN` | `hasAuthority("ADMIN")` when bare authority is intentional. |
| JWT scope `"reports.read"` with default converter | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")`. |
| Custom permission `"invoice:approve"` | `invoice:approve` | `hasAuthority("invoice:approve")`. |
| Custom JWT prefix `"PERM_"` | `PERM_reports.read` | `hasAuthority("PERM_reports.read")`. |

Change a rule only if it reflects business intent; sometimes the mapper needs fixing because the account was **granted the wrong authority**. Changing endpoints to `permitAll()` is a dangerous way to mask bugs.

### 9.3. Testing Only with `@WithMockUser`

`@WithMockUser(roles="ADMIN")` creates `ROLE_ADMIN` in tests. If the production database mapper only emits bare `ADMIN`, tests may pass while the real API returns 403. Include integration tests exercising the **real user source/token converter**, and inspect `Authentication.getAuthorities()` on that request.

### 9.4. Replacing the JWT Converter Unintentionally

When swapping the converter to read `"permissions"`, scopes from `"scope"` may stop being produced if the new converter only reads one claim. An endpoint that previously received `SCOPE_reports.read` may start returning 403. Test both `permissions` and `scope` mappings if both are needed; do not test only the raw claims list.

### 9.5. Mixing Up `hasRole` and `hasAuthority` in Method Security

`@PreAuthorize("hasRole('ADMIN')")` and `@PreAuthorize("hasAuthority('ROLE_ADMIN')")` typically check the same default role, whereas `@PreAuthorize("hasAuthority('ADMIN')")` checks something different. Be careful across request-level DSL and method expressions when a custom role prefix is configured.

### 9.6. Getting 403 from CSRF and Adding More Roles

For POST in the example, even when `analyst` has `SCOPE_reports.write`, omitting the CSRF token still produces 403. Re-test with `.with(csrf())` to separate the two. For apps using only Bearer tokens without automatic cookies, CSRF policy can differ; base enable/disable decisions on the actual threat model, not merely "POST returned 403."

### 9.7. API Returns 200 Yet Exposes Out-of-Scope Data

Having `SCOPE_reports.read` does not mean a user can read every organization's reports. Roles/scopes check **functional** permissions, whereas owner/tenant/ACL checks enforce **record-level** permissions. If a service calls an unscoped `findById(id)`, a user can still read another user's data even when every `hasAuthority` test passes. Filter repository queries by `ownerUserId`/`authorizedTenantId` and write cross-user ID tests.

### 9.8. Misdebugging `SecurityContext` in Async/Background Jobs

`SecurityContextHolder` typically uses thread-bound context; `@Async` code, scheduled jobs, and message consumers do not automatically carry a valid HTTP principal. Never fall back to admin or skip checks when context is absent. For background jobs, propagate verified scope/identity via an appropriate mechanism rather than casually reusing request credentials.

### 9.9. Stale Cached Authorities

A user had a role revoked, yet a session, token, or cache still holds old authorities and endpoints keep allowing access. Conversely, a newly granted permission is missing from an older JWT, causing 403. Plan token TTLs, invalidation/session refresh, and revocation policies according to sensitivity. Never assume a role-table edit immediately updates every circulating token.

## 10. Quick Procedure for Investigating a 403 Case

Suppose a ticket reports: "Admin hits `/api/reports` and gets 403, yet reports still appear in the UI."

**Step 1 — reproduce the request:** record HTTP method, URL, status, request ID, and auth mechanism. Do not copy tokens or passwords into tickets.

**Step 2 — confirm authentication:** test a comparable authenticated endpoint; check whether the request has a real principal and whether password/token validation passed. If it is 401, resolve authentication first.

**Step 3 — inspect effective authorities:** in tests or safe diagnostics, `admin` has `ROLE_ADMIN` but lacks `SCOPE_reports.read`.

**Step 4 — compare against the rule:** `/api/reports` requires `hasAuthority("SCOPE_reports.read")`. Under the current policy, 403 is **the right outcome**. If business requirements want admins to view reports, approve and implement an explicit policy instead of making ad-hoc changes.

**Step 5 — check other layers:** if the scope is present yet 403 persists, check CSRF (for unsafe methods), filter chains, `@PreAuthorize`, data/tenant permissions, custom access decisions, and exception mappers.

**Step 6 — write regression tests:** one positive test (authorized principal gets 200), one negative test (missing authority gets 403); for POST, include with/without CSRF cases; for data access, include owner/tenant cases. Conclude the fix only when tests actually execute through the right chain and provider.

### 10.1. Minimum Verification Matrix

| Case | Test Group | Demo Expectation |
| --- | --- | --- |
| No credentials to `/api/me` | Authentication | 401 |
| Wrong analyst password | Authentication | 401 |
| Admin to `/api/admin` | Role | 200 |
| Analyst to `/api/admin` | Role | 403 |
| Admin to `/api/admin/exact` | Exact `ROLE_ADMIN` | 200 |
| Admin to `/api/admin/strict` | Wrong exact `ADMIN` | 403 |
| Analyst to `/api/reports` | Scope-like authority | 200 |
| Admin to `/api/reports` | Missing scope | 403 |
| Analyst POST export without CSRF | CSRF | 403 |
| Analyst POST export + CSRF | CSRF + authority | 202 |
| Admin POST export + CSRF | Missing scope (not missing CSRF) | 403 |
| `@WithMockUser(authorities="reports.read")` | Wrong scope prefix | 403 |

All of these tests are present in the section 6 suite; they intentionally verify **both allow and deny behavior**, not merely "login succeeded."

## 11. Self-Check Knowledge Questions

**Scenario 1:** `getAuthorities()` contains only `ROLE_SUPPORT`, yet a method uses `hasAuthority('SUPPORT')`. Why 403?  
**Answer:** `hasAuthority` compares exact strings; `SUPPORT` differs from `ROLE_SUPPORT`. Choose `hasRole('SUPPORT')` per default convention or `hasAuthority('ROLE_SUPPORT')` if that matches policy.

**Scenario 2:** JWT has `"scope": "orders.read orders.write"`, default resource server converter, and rule `hasAuthority('orders.read')`. Does it match?  
**Answer:** No; the converter typically produces `SCOPE_orders.read` and `SCOPE_orders.write`. Adjust the rule or converter by design.

**Scenario 3:** `@WithMockUser(roles="ADMIN")` passes, yet HTTP Basic with the real `admin` user gets 403. Is that contradictory?  
**Answer:** No; the mock user automatically gets `ROLE_ADMIN`. Inspect the real user's authorities produced by `UserDetailsService`/provider, the active chain, and role mapping.

**Scenario 4:** A user has `SCOPE_reports.write`, POSTing a report returns 403, and no CSRF token was sent. Are you sure the scope is missing?  
**Answer:** Not yet. Retry the POST with a valid CSRF token; if it succeeds, the cause was CSRF. If it still returns 403, continue investigating permissions/other policies.

**Scenario 5:** Admin has `ROLE_ADMIN`, the API requires `SCOPE_reports.read`, and no role hierarchy/override exists. Should access be allowed automatically?  
**Answer:** No. Roles and scopes are distinct authorities; allow only if an explicit policy permits it.

**Scenario 6:** A token contains `"roles":["ADMIN"]`, yet `Authentication` only has `SCOPE_read`. Why?  
**Answer:** The default JWT converter focuses on scopes; provider-specific role claims do not automatically convert into `ROLE_ADMIN`. Design and test a custom converter if needed.

**Scenario 7:** The principal has the right authority, yet GET still returns 404. Is authorization necessarily wrong?  
**Answer:** Not necessarily. The endpoint may scope queries by owner/organization and intentionally return 404 for out-of-scope records, or the ID may not exist.

**Scenario 8:** A request goes through chain #2, yet the developer edits a rule in chain #1. Outcome?  
**Answer:** The edit has no effect on the request. Check `securityMatcher`, `@Order`, and which filter chain is actually selected.

**Scenario 9:** A user's scope was revoked in the identity provider, yet an old JWT still carries that scope. Where is the gap?  
**Answer:** Tokens are typically a snapshot of permissions at issuance time. You need appropriate TTL, revocation, live permission checks, or token re-issuance policies; editing the DB does not automatically invalidate active tokens.

**Scenario 10:** You observe `authentication.isAuthenticated()==true` on an anonymous token. Can it be treated as a valid login?  
**Answer:** No. Anonymous authentication can report `true`; use the framework's trust resolver or `authenticated()` to distinguish them.

## 12. Practical Checklist

- [ ] Confirm the exact HTTP method, URL, and real status (401/403/404/302).
- [ ] Identify the authentication mechanism: Basic, form, session, JWT, OAuth2/OIDC.
- [ ] Verify the active `SecurityFilterChain`, chain order, and matchers.
- [ ] Inspect **`Authentication.getAuthorities()` directly**, rather than guessing from raw DB/JWT roles or scopes.
- [ ] Check exact `ROLE_`, `SCOPE_`, letter case, dots, and custom authority strings.
- [ ] For `hasRole`, account for the default prefix; for `hasAuthority`, check the exact string.
- [ ] Inspect JWT converters, claim names, and authority prefixes; verify tokens completely.
- [ ] Check role hierarchies, method security, and custom permission evaluators if used.
- [ ] For POST/PUT/PATCH/DELETE, separate CSRF 403s from missing-authority 403s.
- [ ] For private/multi-tenant resources, verify owner/organization scope beyond functional permissions.
- [ ] Write both positive **and** negative tests using the real auth flow, not mock principals alone.
- [ ] Never log raw tokens, passwords, or credentials, or grant extra privileges as a "quick fix."
- [ ] Never use `permitAll()` or disable CSRF to hide bugs without proper design and risk review.
- [ ] Account for cache/session/token lifetimes when changing permissions.
- [ ] Enable security TRACE only in controlled environments and turn it off after investigation.

## 13. Conclusion and Reference Documentation

**The right reasoning chain:** request → authentication → `Authentication.getAuthorities()` → actual chain/rule → CSRF, method security, and owner/tenant checks → decision. Under Spring Security defaults, `hasRole("ADMIN")` looks for `ROLE_ADMIN`, `hasAuthority("ROLE_ADMIN")` checks that exact string, and JWT scope `"reports.read"` is normally mapped to `SCOPE_reports.read`. When a 403 happens, verify every link in the chain and write a control test rather than guessing from role labels in the UI.

Official documentation and standards:

- [Spring Security — HTTP Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet filter architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — OAuth2 JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security — CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750)
