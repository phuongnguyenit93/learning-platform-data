# Testing Unauthenticated, Unauthorized, and Permitted Access

A Spring Boot endpoint can return valid JSON in a unit test and still **allow unauthorized users** in production. Conversely, a test that only asserts status `403` might turn green because of a **missing CSRF token**, rather than because a role or ownership policy is enforced. Security testing therefore must ask not just “is the response 200?”, but must describe **who is calling, which credentials they use, which permissions are required, whose resource they touch, and which operations actually executed**.

This Knowledge lesson belongs to the **Security** section of the **Spring Boot – testing** module, focusing directly on **testing unauthenticated, unauthorized, and permitted access**. We will build a matrix contrasting *anonymous -> 401*, *authenticated but insufficient permissions -> 403*, and *authorized -> 200/202*, then add protection against cross-account access (*Broken Object Level Authorization / IDOR*), CSRF, HTTP method rules, and service-layer permissions.

The examples use **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, JUnit Jupiter 5, Spring Security Test, MockMvc, and @SpringBootTest**. The sample application configures **HTTP Basic** so 401/403 scenarios are easy to observe and real credentials pass through the authentication filter. All sample accounts/passwords live strictly in **test sources**, not in deployment config. In production, many APIs use OAuth2/JWT or mTLS; the same testing principles apply, though status codes, challenges, and token validation must be verified against the **actual security configuration**.

## 1. Learning objectives

After completing this lesson, you will be able to:

- Distinguish **authentication** from **authorization**, and explain why both require tests.
- Understand the typical meaning of HTTP `401 Unauthorized`, `403 Forbidden`, `200 OK`, `202 Accepted`, and cases where `302`/`404` are used by policy.
- Build a security matrix for anonymous callers, invalid credentials, regular users, admins, owners, and non-owners.
- Write a `SecurityFilterChain` with deny-by-default rules and proper `ROLE_` checks.
- Test request-level security with `@WebMvcTest`, `MockMvc`, and the real filter chain.
- Distinguish `@WithMockUser`/`user(...)` **building a mock `SecurityContext`** from `httpBasic(...)` **going through username/password authentication**.
- Test service-level authorization via `@EnableMethodSecurity` and `@PreAuthorize` with ownership.
- Prevent a logged-in user from viewing another account's data.
- Verify that a rejected request **never reaches services that cause side effects**.
- Separate missing-CSRF errors from missing-role errors in POST/PUT/PATCH/DELETE operations.
- Recognize false-green tests caused by disabling filters or mocking the security boundary.
- Understand that JWT tests with `jwt()` do not by themselves prove signature/issuer/audience verification.
- Write positive/negative cases, run the suite, and recognize which boundaries remain untested.

## 2. Foundational mechanism: authentication first, authorization second

**Authentication:** who is the caller and are their credentials valid? With HTTP Basic, username/password are read from the `Authorization` header, passed through the authentication manager/provider, and turned into an `Authentication` if valid. With an OAuth2 resource server, the bearer token is decoded/signature-checked or introspected as configured.

**Authorization:** which **actions** may the authenticated caller perform on which **resources**? For example, only admins view administrative metrics; Alice can read Alice's account, not Bob's. A `SecurityContext` only shows that an identity was recognized; it **does not** automatically make every system object readable.

Diagram:

```text
HTTP request
   |
   v
Spring Security FilterChainProxy
   |
   +-- Authentication
   |     +-- anonymous / invalid credentials
   |     +-- valid Authentication with authorities
   |
   +-- AuthorizationFilter: URL + method rules
   |     +-- /api/admin/** -> ROLE_ADMIN
   |     +-- /api/accounts/** -> authenticated
   |
   +-- CSRF filter for state-changing methods
   |
   v
Controller
   |
   +-- AccountService proxy with @PreAuthorize
   |     +-- admin OR requested owner equals authentication.name
   |
   v
Business operation / DTO
```

**Two layers of authorization:** request matchers block unauthorized routes; method security protects logic invoked from controllers, scheduled jobs, or other services. If only URLs are guarded and another service calls the method directly, data can leak through the bypass path.

## 3. HTTP status map: do not memorize “403 = unauthorized” mechanically

| Scenario in this lesson's HTTP Basic API | Expected response | Why |
|---|---:|---|
| Anonymous calls protected GET | `401` | No valid credentials; Basic entry point sends challenge |
| Wrong username/password | `401` | Authentication failed |
| Authenticated Alice calls admin endpoint | `403` | Identity exists, but lacks `ROLE_ADMIN` |
| Authorized admin calls GET admin | `200` | Authorization permits |
| Alice reads Alice's account | `200` | Permitted by ownership |
| Alice reads Bob's account | `403` | Authenticated, but not the owner |
| Admin reads Bob's account | `200` | Rule grants admin access |
| Admin POSTs without CSRF | `403` | CSRF blocks before business logic, **not** missing `ROLE_ADMIN` |
| Admin POSTs with valid CSRF | `202` | Permitted to queue demo job |
| Anonymous POSTs with CSRF | `401` | CSRF does not replace authentication |

**Read according to your configuration.** If an app uses form login, anonymous access to a protected page may get a **302 redirect** to login instead of 401. For a JWT resource server, `401` often comes with `WWW-Authenticate: Bearer` when tokens are missing/invalid and `403` when scopes are missing; an API with a 404 policy to hide resource existence may also be valid. Tests must assert the **published contract**, rather than applying one status code to every application style.

### 3.1. Why is 401 named “Unauthorized” even though it means unauthenticated?

The historical name `401 Unauthorized` is confusing. In HTTP security practice, `401` normally means credentials are missing or unacceptable and an authentication challenge is required; `403` indicates the server understood the request but refuses permission. A successfully logged-in user lacking permission to read an admin report normally receives `403`.

In the HTTP Basic example, `401` from the entry point typically includes `WWW-Authenticate: Basic ...`. Do not assume this header is always Basic: with Bearer/JWT, the challenge and error details differ.

## 4. Three dimensions of an authorization matrix

A test must describe at least:

1. **Principal:** anonymous, Alice, Bob, admin, or service account.
2. **Action:** GET/POST/PUT/PATCH/DELETE, export, approve, refund.
3. **Resource:** whose account/document, which tenant, which state.

Example matrix:

| Principal | GET `/api/admin/metrics` | POST `/api/admin/reindex` with CSRF | GET `/api/accounts/alice` | GET `/api/accounts/bob` |
|---|---:|---:|---:|---:|
| Anonymous | 401 | 401 | 401 | 401 |
| Alice / USER | 403 | 403 | 200 | 403 |
| Bob / USER | 403 | 403 | 403 | 200 |
| Admin / ADMIN | 200 | 202 | 200 | 200 |
| Wrong password | 401 | 401 | 401 | 401 |

**Note:** For a POST **missing** CSRF, many requests — even from a valid admin — can receive 403, masking the role authorization signal. Therefore, the POST column above **assumes valid CSRF**. Missing CSRF must be tested separately rather than conflating rejection reasons.

### 4.1. “Permitted access” is not just 200

An endpoint creating a resource may return 201, queueing work may return 202, and deleting may return 204. A strong test verifies the status **and the permitted side effects/response data**, instead of hard-coding `200` for every use case. Most importantly, **unauthorized requests must not mutate data**, even if the controller layer eventually happens to return an error code.

## 5. Boundary: URL rules and object-level rules

A rule:

```java
.requestMatchers("/api/accounts/**").authenticated()
```

only proves the caller authenticated to reach the accounts route. It **does not** answer “may Alice GET `/api/accounts/bob`?”. If a controller does:

```java
// ANTI-PATTERN: any logged-in user can read any owner supplied by the URL.
return accountService.readAnything(ownerFromPath);
```

then an **Insecure Direct Object Reference / Broken Object Level Authorization** vulnerability may exist. Tests must include both branches:

- Alice -> Alice: **allowed**, returns Alice properly.
- Alice -> Bob: **denied**, never returns Bob's data.

In multi-tenant systems, checks must also verify `tenantId` from the **trusted authentication context**, not merely compare username against a client-supplied field. Even when roles are valid, object-level constraints must still be enforced.

## 6. Minimal security policy design for this lesson

The demo defines:

- `GET /api/admin/metrics`: `ROLE_ADMIN` only.
- `POST /api/admin/reindex`: `ROLE_ADMIN` and valid CSRF only.
- `GET /api/accounts/{owner}`: must be authenticated; the service allows only the owner or an admin.
- Other routes: **denyAll**.
- Authentication: HTTP Basic.
- CSRF: **kept enabled**; do not disable it just to make POST tests green.
- Users: Alice, Bob (`ROLE_USER`), and admin (`ROLE_ADMIN`) created in test-only configuration.

What this lesson **does not** prove:

- Passwords/roles managed in a production IdP/database.
- JWT validation, token rotation, MFA, federation, or OAuth2 scopes.
- TLS/Basic credentials over the Internet (HTTP Basic **is only safe over HTTPS and with a proper policy**).
- Real account status in a database, because the demo returns static DTOs.
- Real scheduled admin jobs, because the demo uses an intentional counter to verify side effects.
- UI login/redirects, CORS preflight, and Spring WebFlux security.

## 7. The `ROLE_` trap in Spring Security

Spring Security's `hasRole("ADMIN")` checks authority `ROLE_ADMIN` by default, not authority `ADMIN`. A user with:

```text
GrantedAuthority("ROLE_ADMIN") -> hasRole("ADMIN") = true
GrantedAuthority("ADMIN")      -> hasRole("ADMIN") = false
```

In Spring Security Test:

```java
// Create a mock Authentication with authority ROLE_ADMIN:
.with(user("test-admin").roles("ADMIN"))

// Create a mock Authentication with only authority ADMIN:
.with(user("test-admin").authorities(
        new SimpleGrantedAuthority("ADMIN")))
```

These are snippets requiring imports and a `MockMvc` context. These two forms **are not equivalent**. When a system uses scopes like `SCOPE_reports:read`, choose `hasAuthority("SCOPE_reports:read")`; do not switch to `hasRole("reports:read")` unless authorities are mapped accordingly. If a team changes the default role prefix, tests and policies must be updated together.

## 8. Testing the real security filter chain or just mocking a user?

Three distinct tests:

- `@WithMockUser(username="alice", roles="USER")`: Spring Security Test creates an `Authentication` in `SecurityContext`; **skips checking passwords, token signatures, or disabled accounts**. Great for testing **authorization**.
- `mvc.perform(get(...).with(user("alice").roles("USER")))`: request post-processor builds a mock `SecurityContext` for that request; likewise does not verify real credentials.
- `mvc.perform(get(...).with(httpBasic("alice", "alice-pass")))`: sets `Authorization: Basic ...`, letting **`BasicAuthenticationFilter`** and the test context's real authentication provider handle it. Suitable for testing valid/invalid passwords and 401 challenges.

**Do not report “JWT is properly verified” because `@WithMockUser` made a request return 200.** That test does not run signature verification. Similarly, the `jwt()` post-processor builds a fake JWT authentication to test scopes/controllers without verifying signatures; see Section 25.

## 9. CSRF: a `403` does not necessarily mean missing permissions

Spring Security protects state-changing HTTP methods with CSRF by default. When a POST lacks a valid CSRF token, Spring may return `403` **before** role permissions are checked. This creates false confidence in tests:

```java
// WEAK TEST: user lacks permission but also lacks CSRF.
mvc.perform(post("/api/admin/reindex")
        .with(httpBasic("alice", "alice-pass")))
   .andExpect(status().isForbidden());
```

It can stay green **even if you accidentally delete the ADMIN rule**, because CSRF still blocks it. A permission test must add `with(csrf())`:

```java
// Proper authorization test on POST when CSRF is enabled:
mvc.perform(post("/api/admin/reindex")
        .with(httpBasic("alice", "alice-pass"))
        .with(csrf()))
   .andExpect(status().isForbidden());
```

Then a separate test proves admin without CSRF gets 403:

```java
mvc.perform(post("/api/admin/reindex")
        .with(httpBasic("admin", "admin-pass")))
   .andExpect(status().isForbidden());
```

**Do not disable CSRF just to make tests pass.** If an API uses stateless bearer tokens not relying on cookies or implicit browser credentials, the team can evaluate a different CSRF policy. However, HTTP Basic, cookies, and browser-origin requests carry their own risks; disabling CSRF requires a threat model, not an “easier-to-write test” excuse.

## 10. Slice tests and full-context tests: where to check what?

| Goal | Test level | Protects well | Limitation |
|---|---|---|---|
| HTTP URL rules, Basic auth, CSRF | `@WebMvcTest` + `MockMvc` + `SecurityFilterChain` | 401/403/200/202 on MVC routes | Does not load all services/DB |
| Service `@PreAuthorize` and owner | `@SpringBootTest` + real bean | Method proxy is protected | Does not verify HTTP transport |
| Object-level checks over HTTP | `@SpringBootTest` + `@AutoConfigureMockMvc` | Request filters + controller + service | Mock servlet, no TCP |
| Actual username/password | `httpBasic(...)` via filter chain | `PasswordEncoder`/`UserDetailsService` | Test users may differ from prod IdP |
| Real JWT validation | `@SpringBootTest` / targeted security integration with real decoder | Signature/audience/issuer/expired JWT | Needs key/JWK/test IdP |
| Real HTTP/TLS/reverse proxy | `RANDOM_PORT` + HTTP client | Server filter chain, cookies, redirects, TLS setup | Slower, heavier infra |
| Business ownership with DB | Repository/service integration with two owners' data | IDOR, tenant isolation, and data leaks | Needs DB fixtures/migrations |

**`@WebMvcTest` does not load every `@Service` by default.** If security policy has service-layer rules, use a full context or import/mock the necessary beans and **test method security separately with the real bean**. If you only mock the service in `@WebMvcTest` and assert 200/403 at the controller, you **have not proved** the service's business-level access control.

## 11. Runnable project structure

We build a mini API with two areas: admin and account owner. File tree:

```text
security-access-tests/
  settings.gradle
  build.gradle
  src/main/java/com/example/securitylesson/
    SecurityLessonApplication.java
    ApiSecurityConfig.java
    AdminJobService.java
    AdminController.java
    AccountSummary.java
    AccountService.java
    AccountController.java
  src/test/java/com/example/securitylesson/
    TestUsersConfig.java
    AdminAccessMvcTest.java
    AccountAccessIntegrationTest.java
```

Example conventions:

- Java 17, Spring Boot 3.5.x, Spring Security 6.5.x (versions managed by the Boot BOM).
- In-memory users live only in `src/test/java`.
- No database; `AccountService` uses a mock DTO to demonstrate ownership checks.
- Method security **must be enabled**.
- CSRF is kept at its default, even when using HTTP Basic.
- No Docker or real credentials required.

## 12. Gradle project

**`settings.gradle`**

```groovy
rootProject.name = 'security-access-tests'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

**Why is `spring-security-test` needed separately?** It provides `@WithMockUser`, `httpBasic(...)`, `csrf()`, `user(...)`, and security integration utilities. `spring-boot-starter-test` brings JUnit/MockMvc/Mockito but does not replace all of Spring Security Test. The Boot BOM manages compatible versions; avoid forcing `spring-security-test` to a different major version.

**Why not put a production user/password in the build?** The demo defines test credentials in `TestUsersConfig` so HTTP Basic tests pass through a real provider without exposing secrets. These are purely local dummy accounts, not guidance for putting in-memory users into a real application.

## 13. Main application and SecurityFilterChain

**`src/main/java/com/example/securitylesson/SecurityLessonApplication.java`**

```java
package example.securitylesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                SecurityLessonApplication.class, args);
    }
}
```

**`src/main/java/com/example/securitylesson/ApiSecurityConfig.java`**

```java
package com.example.securitylesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers("/api/accounts/**")
                            .authenticated()
                        .anyRequest()
                            .denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }
}
```

**Component breakdown:**

1. `@EnableMethodSecurity` enables Spring AOP evaluation of `@PreAuthorize` on services; Spring Boot starter security **does not enable method security automatically**.
2. `/api/admin/**` requires `ROLE_ADMIN`. This rule **is placed before** broader rules; matcher ordering changes outcomes when patterns overlap.
3. `/api/accounts/**` requires `authenticated`, but **does not check object ownership itself**. The service handles that.
4. `anyRequest().denyAll()` blocks undeclared routes instead of allowing them by default.
5. `httpBasic` configures an authentication entry point so protected unauthenticated GETs receive 401.
6. Form login is disabled in the demo to avoid HTML 302 redirects, keeping API behavior consistent.
7. CSRF remains enabled; POSTs require a valid CSRF token in MockMvc tests.

**Do not assume 403 for every `denyAll`:** for an anonymous caller, `ExceptionTranslationFilter` may invoke the Basic authentication entry point and return 401; for an authenticated user, `denyAll` typically returns 403. The security entry point and exception handling decide the final HTTP status.

## 14. Business service and controller with observable side effects

**`src/main/java/com/example/securitylesson/AdminJobService.java`**

```java
package com.example.securitylesson;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class AdminJobService {

    private final AtomicInteger acceptedReindexRequests =
            new AtomicInteger();

    public int acceptReindexRequest() {
        return acceptedReindexRequests.incrementAndGet();
    }
}
```

This counter only simulates **an easily verifiable side effect in tests**, not a production job scheduler. With a real queue (Kafka/RabbitMQ/DB outbox), integration tests must verify that unauthorized requests **do not publish messages or write rows**. Never use a shared counter as a security mechanism.

**`src/main/java/com/example/securitylesson/AdminController.java`**

```java
package com.example.securitylesson;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final AdminJobService jobs;

    public AdminController(AdminJobService jobs) {
        this.jobs = jobs;
    }

    @GetMapping("/metrics")
    public Map<String, String> metrics() {
        return Map.of("status", "OK");
    }

    @PostMapping("/reindex")
    public ResponseEntity<Map<String, Integer>> reindex() {
        int requestNumber = jobs.acceptReindexRequest();
        return ResponseEntity.accepted()
                .body(Map.of("acceptedRequestNumber", requestNumber));
    }
}
```

A trustworthy `403` test should verify that `jobs.acceptReindexRequest()` **was not called**. This catches regressions where a controller triggers a side effect before checking permissions or when a security filter is removed. If the method affects a database, inspect DB/outbox state after the response as well.

## 15. Object-level authorization: AccountService

**`src/main/java/com/example/securitylesson/AccountSummary.java`**

```java
package com.example.securitylesson;

public record AccountSummary(
        String owner,
        String status) {
}
```

**`src/main/java/com/example/securitylesson/AccountService.java`**

```java
package com.example.securitylesson;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AccountService {

    @PreAuthorize(
            "hasRole('ADMIN') or #owner == authentication.name")
    public AccountSummary read(
            @P("owner") String owner) {

        return new AccountSummary(owner, "ACTIVE");
    }
}
```

**Why `@P("owner")`?** Spring Security SpEL needs to know parameter names. `@P` provides an explicit name, avoiding total reliance on compiler `-parameters` or debug parameter metadata. `authentication.name` is the principal's username in the demo.

**Key takeaway:** `read` returns an illustrative DTO without querying a real DB. It proves `@PreAuthorize` can block a method by object owner. In real systems, ownership must be determined from **trusted database data**, never from caller-declared JSON. For example, if document ID `doc-7` belongs to Bob while the caller passes `owner=alice`, checking owner from the path would fail. The policy must verify `document.ownerId` from a repository or `PermissionEvaluator`. Exercises in Section 30 cover how to upgrade this.

### 15.1. Controller does not duplicate authorization logic

**`src/main/java/com/example/securitylesson/AccountController.java`**

```java
package com.example.securitylesson;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountService accounts;

    public AccountController(AccountService accounts) {
        this.accounts = accounts;
    }

    @GetMapping("/{owner}")
    public AccountSummary read(@PathVariable String owner) {
        return accounts.read(owner);
    }
}
```

The controller merely delegates to the service. The HTTP layer requires `authenticated`, and the service uses method security to decide owner/admin access. Calling `accounts.read("bob")` from another Spring bean also passes through the proxy when invoked **via the bean proxy**, so protection is not limited to the URL alone.

**Self-invocation caveat:** If another method inside `AccountService` calls `this.read("bob")`, it can bypass the Spring AOP proxy and `@PreAuthorize` will not run. In production, design service boundaries carefully and test these bypass paths rather than treating annotations as an absolute guard on every Java call.

## 16. Test-only identities and password encoder

**`src/test/java/com/example/securitylesson/TestUsersConfig.java`**

```java
package com.example.securitylesson;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
public class TestUsersConfig {

    @Bean
    PasswordEncoder testPasswordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService testUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build());
    }
}
```

These passwords exist solely for the **test process**. `@TestConfiguration` is not component-scanned like normal production `@Configuration`; test classes must `@Import(TestUsersConfig.class)`. HTTP Basic tests verify the real provider compares passwords using `PasswordEncoder`; `@WithMockUser` skips this step.

Never ship sample credentials to production, never share an in-memory user database with live environments, and never log passwords. When using a real identity provider, create dedicated sandbox/test users with minimal privileges; never send test probes against customer accounts.

## 17. `@WebMvcTest`: security filters must actually be applied

**`src/test/java/com/example/securitylesson/AdminAccessMvcTest.java`**

```java
package com.example.securitylesson;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AdminController.class)
@Import({ApiSecurityConfig.class, TestUsersConfig.class})
class AdminAccessMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    AdminJobService jobs;

    @Test
    void anonymousGetIs401AndPromptsForCredentials()
            throws Exception {

        mvc.perform(get("/api/admin/metrics"))
                .andExpectAll(
                        status().isUnauthorized(),
                        header().string(
                                HttpHeaders.WWW_AUTHENTICATE,
                                containsString("Basic")));

        verifyNoInteractions(jobs);
    }

    @Test
    void incorrectPasswordIs401() throws Exception {
        mvc.perform(get("/api/admin/metrics")
                        .with(httpBasic("admin", "wrong-pass")))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(jobs);
    }

    @Test
    void authenticatedRegularUserIs403()
            throws Exception {

        mvc.perform(get("/api/admin/metrics")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void actualAdminCredentialsAreAllowed()
            throws Exception {

        mvc.perform(get("/api/admin/metrics")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.status").value("OK"));

        verifyNoInteractions(jobs);
    }

    @Test
    @WithMockUser(username = "fake-admin", roles = "ADMIN")
    void mockAdminRoleIsAlsoAllowedForAuthorizationOnly()
            throws Exception {

        mvc.perform(get("/api/admin/metrics"))
                .andExpect(status().isOk());

        // Mock user bypasses password provider.
    }

    @Test
    void rawAdminAuthorityWithoutRolePrefixIs403()
            throws Exception {

        mvc.perform(get("/api/admin/metrics")
                        .with(user("operator").authorities(
                                new SimpleGrantedAuthority("ADMIN"))))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void adminPostWithoutCsrfIs403ButHasNoSideEffect()
            throws Exception {

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void adminPostWithInvalidCsrfIs403()
            throws Exception {

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("admin", "admin-pass"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void userPostWithValidCsrfStillNeedsAdminRole()
            throws Exception {

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isForbidden());

        verifyNoInteractions(jobs);
    }

    @Test
    void adminPostWithCsrfIsAcceptedAndCallsJobOnce()
            throws Exception {

        when(jobs.acceptReindexRequest()).thenReturn(1);

        mvc.perform(post("/api/admin/reindex")
                        .with(httpBasic("admin", "admin-pass"))
                        .with(csrf()))
                .andExpectAll(
                        status().isAccepted(),
                        jsonPath("$.acceptedRequestNumber").value(1));

        verify(jobs).acceptReindexRequest();
    }
}
```

This class has **10 test methods**. Testing with `@MockitoBean` mocks only **`AdminJobService`**, while `ApiSecurityConfig`, HTTP Basic filters, CSRF filter, MVC routing, and request authorization are real inside the test context. If anonymous 401 or user 403 tests fail because a route was exposed, this suite catches it.

**Why `verifyNoInteractions(jobs)`?** Returning 403 after the service already queued a job is still a security bug. Tests must also assert **zero side effects** at the service boundary. In integration tests with a real DB/queue, assert postconditions on external state as well, since Mockito only observes the mocked bean.

### 17.1. Why must missing-CSRF tests be separate?

Two tests:

- `adminPostWithoutCsrfIs403...`: tests CSRF protection.
- `userPostWithValidCsrfStillNeedsAdminRole`: tests **authorization**.

If you write a user POST without CSRF and only assert 403, you do not know whether the role rule is actually working. The same principle applies to PUT/PATCH/DELETE when CSRF is enabled.

### 17.2. Role tests and password tests protect different things

`actualAdminCredentialsAreAllowed` uses `httpBasic`, passing through the password provider. `mockAdminRoleIsAlsoAllowedForAuthorizationOnly` uses `@WithMockUser`, bypassing credentials to verify the role decision. Both are useful, but neither replaces the other. A `@WithMockUser` test can stay green even when the production password encoder, account lock, or login flow is broken.

## 18. `@SpringBootTest`: testing ownership with the real service

**`src/test/java/com/example/securitylesson/AccountAccessIntegrationTest.java`**

```java
package com.example.securitylesson;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = SecurityLessonApplication.class)
@AutoConfigureMockMvc
@Import(TestUsersConfig.class)
class AccountAccessIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountService accounts;

    @Test
    void anonymousCallerCannotReadEvenOwnLookingPath()
            throws Exception {

        mvc.perform(get("/api/accounts/alice"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsRejectedAtAuthentication()
            throws Exception {

        mvc.perform(get("/api/accounts/alice")
                        .with(httpBasic("alice", "not-the-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadAlice() throws Exception {
        mvc.perform(get("/api/accounts/alice")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.owner").value("alice"),
                        jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    void aliceCannotReadBob() throws Exception {
        mvc.perform(get("/api/accounts/bob")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCanReadBob() throws Exception {
        mvc.perform(get("/api/accounts/bob")
                        .with(httpBasic("bob", "bob-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.owner").value("bob"));
    }

    @Test
    void adminCanReadOtherOwnersAccount()
            throws Exception {

        mvc.perform(get("/api/accounts/bob")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.owner").value("bob"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void directServiceCallCannotBypassOwnerRule() {
        assertThrows(AccessDeniedException.class,
                () -> accounts.read("bob"));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void methodAuthorizationAlsoAllowsAdmin() {
        AccountSummary result = accounts.read("bob");

        assertEquals("bob", result.owner());
    }
}
```

There are **8 test methods**. The last two call the **real `AccountService` bean** (with its method security proxy) directly instead of going only through the controller. This proves the access rule does not live solely in the URL matcher. When `@EnableMethodSecurity` is removed or `@PreAuthorize` is deleted, the test where Alice calls `accounts.read("bob")` will no longer throw `AccessDeniedException` and the suite will fail.

**Important:** `@SpringBootTest + @AutoConfigureMockMvc` builds a broader application context than `@WebMvcTest`, yet `MockMvc` is still a servlet invocation **without a TCP socket**. It is ideal for testing filter chain + controller + real service in one context. If you need real HTTP tests, use `webEnvironment=RANDOM_PORT` with an HTTP client and verify cookies, TLS, or proxies as well.

## 19. Guide to running the project

With Java 17 and a Gradle wrapper (created per project standards), run:

```bash
./gradlew test --tests com.example.securitylesson.AdminAccessMvcTest --tests com.example.securitylesson.AccountAccessIntegrationTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests com.example.securitylesson.AdminAccessMvcTest --tests com.example.securitylesson.AccountAccessIntegrationTest
```

Expected totals:

| Class | `@Test` count | Focus |
|---|---:|---|
| `AdminAccessMvcTest` | **10** | Anonymous/invalid Basic, 403 role, admin 200, CSRF 403, allowed POST 202 |
| `AccountAccessIntegrationTest` | **8** | Anonymous/invalid password, owner vs non-owner, admin, method security proxy |
| **Total** | **18** | Unauthenticated, unauthorized, and permitted states |

`BUILD SUCCESSFUL` is expected when dependency resolution/Java/source match. **This is an expected result after code review, not a claim that Gradle was executed in your repository.** JUnit reports are typically found at `build/reports/tests/test/index.html`.

Even if one test group passes in the IDE, run both in the suite: different test slices/contexts can uncover missing security configuration along an initialization path. Do not retry failed tests using real accounts or passwords.

## 20. Distinguishing authN and authZ tests: reviewer checklist

A request returns 401:

- Is a real filter chain running or did a controller return 401 manually?
- Missing credentials, wrong password, disabled/locked account, expired token, or invalid signature?
- Is there an appropriate protocol `WWW-Authenticate` challenge?
- Does it leak sensitive reasons (“user exists”, “wrong user”)?
- Were any side-effecting database/service calls executed before rejection?

A request returns 403:

- Is the caller already authenticated?
- If it is a POST, is the CSRF token valid **before concluding a missing role**?
- Does the security rule lack `ROLE_` or have a mismatched scope mapping?
- Does the resource belong to another owner/tenant?
- Do method annotations run through a real proxy?
- Does the access-denied response return sensitive data in body/headers?

A permitted request:

- Right role/scope/owner and HTTP method?
- Does the response contain **the right resource**, not just an empty 200?
- Did the permitted side effect occur exactly once?
- Is privilege escalation prevented when altering path/query/body?
- If the logic has a transaction, is the record/outbox state valid?

**Do not stop at an assertion suite that only checks HTTP status.** Data postconditions and “no side effects” give tests genuine security value.

## 21. `@WithMockUser`, `@WithUserDetails`, and `httpBasic`

| Mechanism | Identity source | Exercises real password/decoder? | Best suited for |
|---|---|---|---|
| `@WithMockUser` | Fake principal created by Spring Security Test | **No** | Rule/role/method security |
| `user("alice").roles("USER")` | `MockMvc` `RequestPostProcessor` | **No** | Single-request principal case |
| `@WithUserDetails("alice")` | Loads `UserDetails` from test context | Does not necessarily run password authentication | Custom principal and `UserDetailsService` role mapping |
| `httpBasic("alice","alice-pass")` | Basic header entering filter chain | **Yes**, if real auth provider/filter is configured | Credential success/failure and Basic challenge |
| `jwt()` | Fake `JwtAuthenticationToken` in test | **Does not verify signature** | Scopes/claims authorization with resource server |
| Real signed JWT + decoder | Bearer through filter and real decoder | **Yes** per key/issuer/audience config | Token validation/security integration |

For tests that need to **verify real authentication**, do not rely solely on `@WithMockUser`. For tests that only need to **verify role ownership**, a valid mock principal is usually faster and more focused.

### 21.1. Does `@WithMockUser` clear the SecurityContext after a test?

Spring Security Test uses `WithSecurityContextTestExecutionListener` to set up context before a method and clean it up afterward. Do not store `SecurityContextHolder` in a static field. If the application puts `Principal` into a custom `ThreadLocal`/MDC or executor, clean up those contexts separately; Spring Security Test cannot manage arbitrary mutable state created by your code.

## 22. Method security and self-invocation

`@PreAuthorize` works on Spring-managed beans via a proxy. For example:

```java
@Service
class ServiceA {

    @PreAuthorize("hasRole('ADMIN')")
    public void privileged() { }

    public void outer() {
        this.privileged(); // WARNING: may bypass proxy
    }
}
```

This is an illustrative snippet, not a file in the demo. With proxy-based Spring AOP, self-invocation does not pass through the proxy interceptor and can skip `@PreAuthorize`. A test calling `accounts.read(...)` from outside the bean (as in Section 18) guards the external path, but does not automatically catch internal call paths. When application code calls methods on the same bean, extract the method into a separate bean or design an appropriate authorization layer, and write a regression test for that exact path.

Similarly, method security on an object instantiated with `new AccountService()` outside the Spring container **runs without a proxy**. Testing a raw Java object only verifies domain logic and must not be used as proof that Spring enforced the annotation.

## 23. Beware of `@WebMvcTest` omitting SecurityFilterChain

A test:

```java
@WebMvcTest(AdminController.class)
@AutoConfigureMockMvc(addFilters = false)
class WeakSecurityTest {
    // ...
}
```

is an **anti-pattern** when the goal is testing authentication/authorization: `addFilters=false` removes security filters, so the test no longer observes HTTP-layer rules. Likewise, if `@WebMvcTest` does not import the custom `SecurityFilterChain` used in production, it may run a **different default security configuration**; 401/403 assertions then no longer prove the real policy.

In the demo we used:

```java
@WebMvcTest(AdminController.class)
@Import({ApiSecurityConfig.class, TestUsersConfig.class})
class AdminAccessMvcTest {
    // ...
}
```

Thus URL/CSRF rules come from the same security config class as the application. In production setups with multiple `SecurityFilterChain` beans using `securityMatcher`, explicitly test rule ordering, chain selection, management endpoints, and path prefixes; never assume one chain applies to all requests.

### 23.1. Mock only what needs to be mocked

In MVC tests, mock the side-effecting service (`AdminJobService`) to verify zero calls; **do not mock `SecurityFilterChain` or the authorizer under test**. In full context, use the real `AccountService` + `@PreAuthorize`. Tests with misplaced boundaries often stay green because “the mock always decides allowed” instead of testing policy.

## 24. Resource existence, ownership, and 404 vs 403

An API may avoid revealing that “Bob's account/document exists” to user A by returning **404** instead of 403 in certain cases. This is a **product and security policy**, not a universal Spring Security rule.

When choosing 404 to hide resources:

- Permitted owner + resource exists -> 200.
- Permitted owner + resource missing -> 404.
- Non-owner accesses existing resource -> 404 (if policy hides existence).
- Anonymous may still get 401 when authentication is mandatory.
- Internal logs can record the reason safely; the public response does not reveal the owner.
- Time-based side channels and error response differences must be evaluated.

**Do not change expected 403 to 404 merely because a test fails.** Document the contract explicitly and test **exactly what the application promises**. The demo picks 403 to help learners distinguish states and has no database resource-not-found scenario.

## 25. JWT Resource Server: 401/403 are not identical to HTTP Basic

With an OAuth2 resource server using Bearer JWTs:

- Missing or invalid Bearer tokens typically result in 401 with a Bearer challenge.
- An authenticated JWT lacking an authority/scope typically results in 403.
- Claims `scope`/`scp` may map to `SCOPE_x`; `ROLE_ADMIN` does not automatically come from a `roles` claim unless a converter is configured.
- Access denial is decided by `AuthorizationManager` and method security; security filters must be included in tests.
- JWT signature/issuer/audience/clock skew must be tested with a real decoder in integration tests.

**Snippet for an API with a real resource server configured**:

```java
// Illustrative only; not for direct use with the HTTP Basic demo config.
// Requires spring-security-test and a SecurityFilterChain using JWT resource server.
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports:read"))))
   .andExpect(status().isOk());
```

This test **does not prove the JWT has a valid signature** because `jwt()` puts a fake `Authentication` into `SecurityContext`. To test invalid signature/issuer/audience/expiry, send a **real Bearer token signed with a test key**, run a real `JwtDecoder`/opaque token introspector or mock at the chosen boundary, and assert behavior explicitly. Do not copy production keys or JWTs into fixtures.

### 25.1. Do not confuse scope 403 with CSRF 403

If a bearer token is sent on a POST while CSRF is enabled, missing CSRF can still cause 403 **before** scopes are checked. When testing authorization, account for the API's specific CSRF policy; do not blindly add `csrf()` if the app is designed as stateless bearer-only with CSRF intentionally analyzed and disabled.

## 26. Matrix of negative cases by role and data

| Scenario | Expected test outcome | Risk caught |
|---|---|---|
| No `Authorization` | 401 | Anonymous access |
| Basic wrong password | 401 | Authentication bypass |
| Valid user missing admin role | 403 | Privilege escalation |
| Authority `ADMIN` missing prefix | 403 under `hasRole` policy | Wrong role mapping |
| Admin GET metrics | 200 | False deny |
| User GET own account | 200 | False deny / owner logic |
| User GET someone else's account | 403 | IDOR |
| Admin GET someone else's account | 200 | Role override |
| Admin POST without CSRF | 403 | CSRF protection |
| User POST with CSRF | 403 | Authorization not masked by CSRF test |
| Admin POST with CSRF | 202 and service called once | Permitted operation |
| Denied POST | No service call / no DB write | Side effect before deny |
| Direct method call bypassing controller | Proper deny/allow | Business layer bypass |
| JWT missing scope | 403 (JWT API contract) | Scope mapping |
| JWT wrong issuer/signature | 401 (real decoder test) | Token validation |
| Disabled user | 401 / contract error | Account status bypass |
| Cross-tenant resource | 403/404 per policy | Multi-tenant leakage |
| Disallowed HTTP verb | 403/405 per matcher/mapping | HTTP method bypass |
| Public endpoint | 200 without auth, if truly public | Overblocking |
| Exception dispatch/forward | No bypass | Dispatcher-type security gaps |

**Not all scenarios belong to the HTTP Basic demo.** A production suite should apply rows matching its threat model/auth mechanism and document why unrelated rows are omitted.

## 27. What data should security tests run on?

For genuine ownership testing, seed at least:

- User A with account/document A.
- User B with account/document B.
- An admin user permitted to view multiple resources.
- A resource from another tenant with a hard-to-guess ID and a predictable ID (to catch path swapping).
- A locked/archived resource if status affects permissions.
- An operation with side effects writing a row/outbox/event to assert forbidden requests never touch state.

If tests use a real DB, query postconditions after a denied request:

```sql
SELECT COUNT(*) FROM audit_events
WHERE actor_id = 'alice' AND action = 'DELETE_BOBS_DATA';
```

Expected count is 0 when Alice is forbidden. This is an illustrative SQL snippet; database/fixtures/columns must match your real schema, and it must never be run against production. With an event broker, verify no message was published to the test topic or use outbox readback. Mock interaction checks are cheap, but they cannot replace data store postconditions.

### 27.1. “Allowed” tests that are still weak

`assert status=200` does not guarantee the permitted response returned the right owner's data. A bug could return 200 with Bob's account for Alice's request. Assert the DTO owner/id/tenant and permitted fields. For list APIs, verify **zero items from other tenants**, even if a query filter was forgotten.

## 28. Security context isolation and concurrency

Spring Security typically stores `SecurityContext` per request/thread. In tests:

- `@WithMockUser` cleans up `SecurityContext` after the method via the test listener.
- Never place the current user in a static field or singleton mutable state.
- With `@Async`/`CompletableFuture`/thread pools, `SecurityContext` does not propagate automatically to every thread. Use `DelegatingSecurityContextExecutor` or properly designed task decorator/propagation infrastructure.
- Never accidentally reuse User A's `Authentication` for Request B due to an un-cleared `ThreadLocal`.
- With Reactor/WebFlux, use `ReactiveSecurityContextHolder` rather than relying on servlet `ThreadLocal`.
- Never print tokens/principal secrets to logs.

**Valuable concurrency test:** two users A/B send concurrent requests to two owners; capture responses and DB state to prove A never receives B's data. A sequential A-then-B unit test catches simple stale singleton state, but does not prove safety under thread races.

### 28.1. Do not hide test issues with `@DirtiesContext`

If Test A pollutes `SecurityContextHolder` or global state, `@DirtiesContext` restarts Spring beans and may make the suite pass, without fixing the cleanup or thread-local bug. Use listeners, request scope, and explicit clearing/restoration; only use `@DirtiesContext` when the bean context state itself must be discarded.

## 29. HTTP methods, matcher order, and deny-by-default

There are three kinds of rules:

1. Route-specific: `/api/admin/**` admin only.
2. Generic authenticated: `/api/accounts/**` authenticated user.
3. Fallback: `anyRequest().denyAll()`.

Order is critical: if `anyRequest().permitAll()` is placed first, admin rules may never apply. Likewise, a filter chain with `securityMatcher("/api/**")` alongside a chain for actuator can affect endpoints outside the matcher.

**Tests need both negatives and positives**: if every request returns 403, the system is “strict” yet suffers **false deny**; if every request returns 200, it is convenient yet unsafe. For method-sensitive authorization, such as GET reading an account vs POST deleting, use `requestMatchers(HttpMethod.DELETE, "/api/accounts/**")` and test every verb. Never use a GET test as proof that DELETE is also protected.

### 29.1. CORS preflight and OPTIONS

Browsers may send `OPTIONS` preflight before cross-origin requests. When an app configures CORS, a preflight is not a business API call; 401/403/200/204 on preflight depends on CORS/security configuration. Do not interpret a preflight 403 as a missing user role. Test trusted origins, methods, headers, credentials, and actual requests separately, especially when CORS and CSRF coexist.

## 30. Self-assessment exercises

### Exercise A — 401 or 403?

An unauthenticated user calls `GET /api/admin/metrics`. A logged-in user with `ROLE_USER` calls the same URL. Under the demo's HTTP Basic config, what responses occur?

**Answer:** Anonymous gets 401 with a Basic challenge; authenticated user lacking `ROLE_ADMIN` gets 403.

### Exercise B — admin POST still returns 403

An admin sends valid credentials on POST `/api/admin/reindex` and gets 403. Why can this happen despite a valid role? Which tests distinguish the causes?

**Answer:** Missing/invalid CSRF. Add `with(csrf())` to test authorization; test missing CSRF separately to verify the CSRF filter.

### Exercise C — mock user vs password

A `@WithMockUser(roles="ADMIN")` test passes even though the admin's database password was disabled. Can you conclude production login/authentication works?

**Answer:** No. Mock user bypasses the authentication provider. Use HTTP Basic/form login/JWT through filters with a real provider/decoder and disabled-account fixtures.

### Exercise D — owner privilege escalation

Alice accesses `/api/accounts/bob` and receives 200. Why is `requestMatchers("/api/accounts/**").authenticated()` insufficient? Where should this be fixed?

**Answer:** The rule only requires being logged in; it does not check ownership. Add owner/tenant authorization in the service/repository and assert Alice->Bob returns 403/404 per contract without leaking Bob's data.

### Exercise E — method security not running

You added `@PreAuthorize`, yet tests still let Alice read Bob. What should you investigate?

**Answer:** Whether `@EnableMethodSecurity` is present; whether the bean is a Spring proxy; self-invocation; SpEL parameter name resolution; whether the service was mocked or created with `new`; whether calls go through the proxy.

### Exercise F — role name

A principal only has authority `ADMIN`, and the rule uses `hasRole("ADMIN")`. Is access allowed? Which API should the rule use if you want to check an unprefixed authority?

**Answer:** Not by default. `hasRole` expects `ROLE_ADMIN`. To check literal `ADMIN`, use `hasAuthority("ADMIN")` per policy.

### Exercise G — denied yet side effect happened

A controller calls `jobs.enqueue()` before checking roles and returning 403. Does asserting status 403 catch this?

**Answer:** No. Assert `verifyNoInteractions(jobs)` or verify DB/outbox state remains unchanged for denied requests.

### Exercise H — JWT signature testing

A test `mvc.perform(get(...).with(jwt()))` returns 200. Does it prove expired tokens or invalid signatures are rejected?

**Answer:** No. `jwt()` injects a fake principal into `SecurityContext`. Real tests through `JwtDecoder`/introspection with invalid/expired/signed tokens are required.

### Exercise I — direct service call

A batch job invokes `AccountService.read("bob")` under Alice's security context without going through MVC. If rules are only on URLs, is data safe?

**Answer:** Not necessarily. Method-level authorization and trusted resource ownership must be enforced at the service boundary (or a central authorization component).

### Exercise J — false deny

After tightening security, both Alice->Alice and Alice->Bob return 403. With only the negative Alice->Bob test, the suite stays green. Is this acceptable?

**Answer:** No. Positive owner->owner and admin->other-owner tests are needed to catch overblocking.

### Exercise K — 404 to hide resources

An API wants to avoid revealing to user A whether Bob owns `doc-7`. Should tests expect 403 or 404?

**Answer:** Follow the decided API security contract, which may specify 404 to hide existence. Never change expected statuses merely to avoid fixing access rules.

### Exercise L — disabling filters

A developer adds `@AutoConfigureMockMvc(addFilters=false)` so controller tests pass. Is this proof the API is secure?

**Answer:** No. Removing security filters stops tests from executing real HTTP authentication/authorization; re-enable filters and import the proper `SecurityFilterChain`.

## 31. Practical troubleshooting

| Symptom | Common cause | How to check |
|---|---|---|
| Anonymous returns 200 | Overbroad `permitAll` or filters disabled | Is `SecurityFilterChain` applied? |
| Anonymous returns 302 instead of 401 | Form login/redirect entry point | Inspect actual `AuthenticationEntryPoint` |
| Anonymous POST returns 403 instead of 401 | CSRF filters request before auth | Test with CSRF, then assert 401 |
| Valid user always gets 401 | Wrong password encoder/provider/credentials | `httpBasic` and `TestUsersConfig` |
| User lacking role gets 200 | Matcher order / overbroad rule | URL rules, `ROLE_ADMIN` |
| Admin with `ROLE_ADMIN` gets 403 | CSRF, another URL rule, method security | GET vs POST, CSRF token |
| Raw `ADMIN` authority fails rule | `ROLE_` prefix | `hasRole` vs `hasAuthority` |
| Alice can read Bob | Missing IDOR/business owner guard | Service `@PreAuthorize` + DB ownership |
| `@PreAuthorize` is ignored | Not enabled, self-invocation, unproxied bean | `@EnableMethodSecurity`, bean wiring |
| `@WithMockUser` passes but real login fails | Authentication bypassed by mock | Real provider/decoder integration |
| JWT test passes yet invalid signature accepted | `jwt()` bypassed decoder | Real `JwtDecoder` tests |
| CSRF tests green yet authorization broken | User POST lacked CSRF | Add CSRF to isolate authZ |
| Denied test still writes DB | Side effect before authorization | Assert no calls / DB unchanged |
| Single test passes, suite fails | `SecurityContext`/custom `ThreadLocal` leak | Reset/context isolation |
| `WebMvcTest` loads different default chain | Missing `@Import` config | Import proper `SecurityConfig` |
| `OPTIONS` blocked unexpectedly | CORS preflight unconfigured | CORS/security matching |
| Response returns sensitive error details | Exception handler leaks internals | Sanitized error contract |
| Full-context test is slow | Wide Boot app context | Slices for URL checks, full for owner/service |

### 31.1. Suggested debugging path

1. Confirm the **right filter chain** handled the request path/method.
2. Confirm input credentials and authentication mechanism without logging passwords/tokens.
3. Confirm the actual `Authentication` name and authorities.
4. Check role prefixes, scope conversions, and tenant context.
5. For POST/PATCH/DELETE, check CSRF before concluding role denial.
6. If an endpoint returns unexpected 200, check URL matchers and method-level guards.
7. If object-level access fails, check the ownership source from trusted DB/domain data.
8. If tests use mocks, locate where security policy is mocked or bypassed.
9. Check side effects of denied requests on services/databases.
10. Run negative + positive tests in the same suite to catch overblocking regressions.

## 32. Pre-merge review checklist

- [ ] At least one **anonymous** test exists for protected routes.
- [ ] **Invalid credentials** tests go through the appropriate authentication provider/decoder.
- [ ] **Authenticated but under-privileged** tests cover role/scope policies.
- [ ] **Authorized access** tests exist, not just 403 checks.
- [ ] Role/authority `ROLE_` and `SCOPE_` mappings are consistent.
- [ ] Real `SecurityFilterChain` is loaded in HTTP security tests.
- [ ] MockMvc filters are not disabled when testing authentication/authorization.
- [ ] `@WithMockUser` is not mistaken for password or JWT signature verification.
- [ ] CSRF is tested separately on unsafe HTTP methods.
- [ ] Denied POST tests include valid CSRF to isolate role denial.
- [ ] Service/business-level tests cover ownership/tenant/ID-based access.
- [ ] Tests verify Owner A cannot read/edit/delete Owner B's resources.
- [ ] Tests verify admin/service roles have permitted access per contract.
- [ ] Unauthorized/forbidden operations **produce zero side effects**.
- [ ] 403 is not arbitrarily swapped for 404 without an existence-hiding API contract.
- [ ] Method security has `@EnableMethodSecurity` and calls pass through Spring proxies.
- [ ] Self-invocation or `new`-created objects are not used as evidence of method security.
- [ ] API uses deny-by-default and rule ordering is tested.
- [ ] Authentication principals/credential fixtures live in test-only configuration.
- [ ] Tests do not use production secrets or users.
- [ ] Error responses do not leak tokens, user enumeration, or internal details.
- [ ] CORS/`OPTIONS`, redirects, and reverse proxies are tested if in the threat model.
- [ ] On JWT APIs, real issuer/audience/signature/expiry validation tests exist.
- [ ] Concurrent requests do not leak `SecurityContext` or tenant data.
- [ ] Evidence exists for DB/queue state on security-sensitive side effects.

**Conclusion:** A meaningful security test suite must test all **three branches**: unauthenticated callers **blocked**, authenticated yet under-privileged callers **denied**, and authorized callers **able to perform the exact permitted action**. Asserting 401/403/200 alone is insufficient: isolate the **reason** for denial (CSRF, authentication, role, or ownership), run the real filter chain/bean proxy, verify zero side effects after denied requests, and validate JWTs/tokens at the real boundary when that is the production auth mechanism. A single test letting owner A read A while denying B is often worth more than dozens of tests only asserting “the admin endpoint returned 403”.

### Official references

- Spring Boot 3.5 — Auto-configured MVC tests, @WebMvcTest, and @SpringBootTest: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Security 6.5 — HTTP Basic authentication and 401 challenge: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — HTTP request authorization, hasRole/hasAuthority/denyAll: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method security @EnableMethodSecurity/@PreAuthorize: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security — Testing method security and @WithMockUser/@WithUserDetails: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Security — Testing HTTP Basic with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF with with(csrf()): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — MockMvc and Spring Security setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- OWASP API Security Top 10 — Broken Object Level Authorization (API1): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- RFC 9110 — HTTP status semantics 401, 403, 404: https://www.rfc-editor.org/rfc/rfc9110
