# Testing Unauthenticated, Authorized, and Unauthorized Requests

In Spring Security (Servlet), a properly protected endpoint must handle **at least three distinct states**: an **unauthenticated** caller, an **authenticated caller with sufficient permissions**, and an **authenticated caller lacking permissions**. HTTP testing needs to prove all three along the real request path, including the security filter chain, authentication mechanism, authorization rules, and HTTP response. Checking only a single successful call is not enough to conclude an endpoint is secure.

This lesson belongs to the **HTTP Testing** group of the **Spring Security - authorization** module. The examples use **Spring Boot 3.x, Spring Security 6.x, Java 17+**, JUnit 5, and MockMvc, with a `SecurityFilterChain` using HTTP Basic so 401/403 outcomes are easy to observe. When switching to form login, OAuth2 Bearer, or a custom entry point, keep the same testing goals while adjusting HTTP expectations to the actual configuration.

## 1. Three States and What Must Be Proven

| Request state | Example | What needs to be proven | Typical HTTP in the Basic example |
| --- | --- | --- | --- |
| **Unauthenticated** | No `Authorization` sent when reading a role-protected report | Protected resource is not returned; the system demands authentication | `401 Unauthorized`, with `WWW-Authenticate: Basic ...` |
| **Authenticated, authorized** | `analyst` with `ROLE_ANALYST` reads report | Request passes authentication and authorization, receives permitted data | `200 OK` with expected content |
| **Authenticated, unauthorized** | `viewer` with `ROLE_VIEWER` reads report requiring `ANALYST` | Denied; does not execute protected action or leak sensitive content | `403 Forbidden` |
| **Invalid credentials** | Valid username, wrong password | Authentication fails; not treated as a logged-in user | `401 Unauthorized` |
| **Authorized but missing CSRF token** | `admin` POSTs to a state-changing endpoint without a token | CSRF protection blocks request before executing the action | `403 Forbidden` under default config |

Distinguish the two concepts:

- **Authentication** answers *who is the principal, and are the credentials valid?*; for example, `BasicAuthenticationFilter` and `AuthenticationManager` validate username/password.
- **Authorization** answers *what actions is this principal allowed to perform on which resources?*; for example, `AuthorizationFilter` enforces `authorizeHttpRequests` or method security evaluates `@PreAuthorize`.

A 403 does not always mean *missing role*: it can also be caused by CSRF, another rule, method security, or object-level permission checks. Similarly, in an application using `formLogin`, anonymous callers may be redirected `302` to a login page; with Bearer tokens, challenges may use `WWW-Authenticate: Bearer ...`. Therefore, tests must verify **the intended rule**, then assert the corresponding status/headers.

## 2. Goals of a Reliable HTTP Security Test

A solid test verifies simultaneously:

1. **Right path and method**: `GET /api/reports/summary` differs from `POST /api/admin/publish` and differs from `GET /api/admin/audit`.
2. **Right authentication mechanism**: anonymous, valid/invalid Basic credentials, or valid token/session per the app.
3. **Right role/authority**: distinguishes `ROLE_ANALYST`, `ROLE_VIEWER`, `ROLE_ADMIN`; does not equate being logged in with having permission.
4. **Right HTTP code and headers**: 401 responses carry the proper challenge; 403 responses never masquerade as 200; 302 is only expected when login redirect applies.
5. **Right success payload**: not just `status().isOk()`; check that the data/DTO contains permitted fields.
6. **No data leakage on denial**: check that body/headers do not contain protected business data.
7. **No side effects on denial**: POST/DELETE must prove data did not change or the service was not called when permission/CSRF is invalid.
8. **Test reliability**: real security config is loaded, the filter chain participates, and filters are not accidentally disabled when building MockMvc.

**Testing surface:** MockMvc simulates Servlet requests in-process, running through `FilterChainProxy` and Spring MVC without **opening a real HTTP port**. It is effective for testing authentication, authorization, and response contracts; it does not replace testing HTTPS, reverse proxies, cookie domains, CORS, load balancers, or real IAM systems in an integration environment.

## 3. Defining the Permission Matrix Before Writing Tests

Suppose the application has three in-memory accounts for learning:

- `analyst/pw` with role `ANALYST`: reads reports.
- `viewer/pw` with role `VIEWER`: can log in but cannot read reports or admin functions.
- `admin/pw` with role `ADMIN`: reads reports, reads audit logs, and publishes admin documents.

Rules in the example:

| Endpoint | Anonymous | ANALYST | VIEWER | ADMIN |
| --- | --- | --- | --- | --- |
| `GET /api/public` | 200 | 200 | 200 | 200 |
| `GET /api/reports/summary` | 401 | 200 | 403 | 200 |
| `GET /api/admin/audit` | 401 | 403 | 403 | 200 |
| `POST /api/admin/publish` (valid CSRF) | 401 | 403 | 403 | 200 |
| `POST /api/admin/publish` (missing CSRF) | 403 | 403 | 403 | 403 |

This is **the sample configuration's matrix**, not a universal rule for all apps. Spring Security's filter ordering causes a POST missing a CSRF token to be blocked with 403 even without authentication credentials. Passing a valid CSRF token on the POST makes the anonymous 401 or insufficient-permission 403 branch visible.

Each row needs at least one representative test, and every privileged endpoint needs both **positive** (allowed) and **negative** (blocked) tests. For multi-tenant or object-level permissions, the matrix must also include **owner, non-owner, different tenant, resource state, and permission expiry**.

## 4. Preparing a Runnable Spring Boot 3.x App

Use a Servlet Spring Boot project with the Gradle plugin and Java 17+. Dependencies in `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter and Spring Boot Test/MockMvc; `spring-security-test` provides `httpBasic()`, `csrf()`, `user()`, `@WithMockUser`, and other security test utilities. In Gradle, the project needs to run JUnit Platform; Spring Boot plugin/starter templates typically configure:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 4.1. Complete Application and SecurityFilterChain

Create `src/main/java/com/example/authorization/HttpAuthorizationApplication.java`:

~~~java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class HttpAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpAuthorizationApplication.class, args);
    }

    @GetMapping("/api/public")
    public String publicData() {
        return "public";
    }

    @GetMapping("/api/reports/summary")
    public String reportSummary() {
        return "report:ready";
    }

    @GetMapping("/api/admin/audit")
    public String auditSummary() {
        return "admin:audit";
    }

    @PostMapping("/api/admin/publish")
    public String publish() {
        return "published";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports/summary")
                            .hasAnyRole("ANALYST", "ADMIN")
                        .requestMatchers(HttpMethod.GET, "/api/admin/audit")
                            .hasRole("ADMIN")
                        .requestMatchers(HttpMethod.POST, "/api/admin/publish")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("analyst")
                        .password("{noop}pw").roles("ANALYST").build(),
                User.withUsername("viewer")
                        .password("{noop}pw").roles("VIEWER").build(),
                User.withUsername("admin")
                        .password("{noop}pw").roles("ADMIN").build()
        );
    }
}
~~~

**Explanation of key decisions:**

- `permitAll()` allows public access; it does not require clients to log in. Do not assume every endpoint needs to return 401 for anonymous.
- `hasAnyRole("ANALYST", "ADMIN")` requires either `ROLE_ANALYST` or `ROLE_ADMIN`. `User.roles("ADMIN")` adds the `ROLE_` prefix; do not declare `roles("ROLE_ADMIN")` when using the short-name role API.
- `hasRole("ADMIN")` blocks authenticated principals lacking `ROLE_ADMIN`. `.anyRequest().denyAll()` locks down routes/methods without published rules.
- `httpBasic(Customizer.withDefaults())` verifies credentials via the `Authorization: Basic ...` header; systems using Basic must run over HTTPS in real environments.
- Not calling `csrf.disable()` keeps default CSRF protection active for unsafe methods such as POST. This enables writing tests that distinguish **missing permission** from **missing CSRF token**.
- The `{noop}pw` password is only for local/test demos; production requires proper password hashing, credentials from a real authentication source, and no hardcoded accounts in code.

Controllers return fixed strings so tests can assert **exact content** without external data dependencies. The app has no database; when moving to real business logic, also test per-record read permissions and verify denials cause no side effects.

## 5. MockMvc Test Suite Running with Spring Security

Create `src/test/java/com/example/authorization/HttpAuthorizationTests.java`:

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAvailableWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadProtectedReport() throws Exception {
        mvc.perform(get("/api/reports/summary"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic ")));
    }

    @Test
    void analystCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("analyst", "pw")))
                .andExpect(status().isOk())
                .andExpect(content().string("report:ready"));
    }

    @Test
    void viewerHasLoginButNotReportPermission() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("viewer", "pw")))
                .andExpect(status().isForbidden());
    }

    @Test
    void analystCannotReadAdminAudit() throws Exception {
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("analyst", "pw")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminAudit() throws Exception {
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("admin", "pw")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin:audit"));
    }

    @Test
    void adminCanAlsoReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("admin", "pw")))
                .andExpect(status().isOk())
                .andExpect(content().string("report:ready"));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/reports/summary")
                        .with(httpBasic("analyst", "wrong")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic ")));
    }

    @Test
    void adminPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("admin", "pw")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithValidCsrfIsAllowed() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("admin", "pw"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("published"));
    }

    @Test
    void viewerPostWithValidCsrfStillHasNoPermission() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("viewer", "pw"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPostWithValidCsrfMustAuthenticate() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(csrf()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminPostWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/admin/publish")
                        .with(httpBasic("admin", "pw"))
                        .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());
    }
}
~~~

### 5.1. Why Keep `@AutoConfigureMockMvc` and Security Filters?

`@SpringBootTest` loads the application context with the configured `SecurityFilterChain`, controller, and `UserDetailsService`. `@AutoConfigureMockMvc` creates MockMvc integrated with the application's filter chain; `addFilters=true` by default. Therefore, requests using `httpBasic("analyst", "pw")` go through Basic authentication, and `AuthorizationFilter` checks authorities before invoking the controller.

If you manually construct `MockMvcBuilders.standaloneSetup(controller)` without attaching Spring Security, tests can return 200 for anonymous requests even though production blocks with 401. For manual MockMvc setup using `webAppContextSetup`, apply `SecurityMockMvcConfigurers.springSecurity()` to add security filters and test post-processors. With `@WebMvcTest`, explicitly verify which security configuration is loaded and add appropriate imports/mocks; it does not automatically substitute for full-chain integration tests.

### 5.2. Why Use `httpBasic()` Instead of Pre-Setting Users for All Three Branches?

`SecurityMockMvcRequestPostProcessors.httpBasic(...)` generates a properly formatted HTTP `Authorization` Basic header so the authentication filter processes real users/passwords in the test application context. This verifies that **wrong passwords return 401**.

`@WithMockUser` or `.with(user("analyst").roles("ANALYST"))` is very useful when you only need to simulate a principal for fast **authorization** tests; they do not prove that passwords are verified, token signatures are valid, or authentication filters run properly. Do not use `@WithMockUser` on anonymous or wrong-password tests and think you tested the HTTP Basic path. With JWT/OAuth2, `jwt()`/`oauth2Login()` helpers exist, but mock principals/claims still do not replace tests with real tokens and a real resource-server decoder.

## 6. Running Tests and Understanding the Output

At the root of the Spring Boot project with Gradle wrapper:

~~~bash
./gradlew test --tests com.example.authorization.HttpAuthorizationTests
~~~

On Windows use:

~~~powershell
.\gradlew.bat test --tests com.example.authorization.HttpAuthorizationTests
~~~

When all properly configured tests pass, Gradle finishes the test task successfully. The section above defines **13 test methods**, verifying these states:

| Test | Expectation | Meaning |
| --- | --- | --- |
| `publicEndpointIsAvailableWithoutLogin` | 200 and `public` | Public resource |
| `anonymousCannotReadProtectedReport` | 401 and Basic challenge | Anonymous blocked |
| `analystCanReadReport` | 200 and `report:ready` | Sufficient permission |
| `viewerHasLoginButNotReportPermission` | 403 | Logged in, missing permission |
| `analystCannotReadAdminAudit` | 403 | `ANALYST` permission does not imply `ADMIN` |
| `adminCanReadAdminAudit` | 200 and `admin:audit` | Valid `ADMIN` permission |
| `adminCanAlsoReadReport` | 200 and `report:ready` | Route permits multiple roles |
| `wrongPasswordIsAuthenticationFailure` | 401 and challenge | Invalid credentials |
| `adminPostWithoutCsrfIsForbidden` | 403 | CSRF blocks even though `ADMIN` has role |
| `adminPostWithValidCsrfIsAllowed` | 200 and `published` | Sufficient permission and CSRF present |
| `viewerPostWithValidCsrfStillHasNoPermission` | 403 | Has CSRF, still lacks permission |
| `anonymousPostWithValidCsrfMustAuthenticate` | 401 | Having CSRF does not replace login |
| `adminPostWithInvalidCsrfIsForbidden` | 403 | Invalid token is also blocked |

For example, tests fail if someone accidentally changes `.requestMatchers(HttpMethod.GET, "/api/reports/summary").hasAnyRole(...)` to `.permitAll()`: the anonymous test can flip from 401 to 200, and the viewer test from 403 to 200. That is a **security regression**; do not edit tests to expect 200. When the authorization contract genuinely changes per an approved requirement, update the matrix and both positive/negative tests.

To test HTTP manually after running `./gradlew bootRun`:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports/summary
curl -i -u analyst:pw http://localhost:8080/api/reports/summary
curl -i -u viewer:pw http://localhost:8080/api/reports/summary
curl -i -u admin:pw http://localhost:8080/api/admin/audit
curl -i -u analyst:wrong http://localhost:8080/api/reports/summary
~~~

The GET calls here return **200, 401, 200, 403, 200, 401** respectively; on 401 endpoints, observe `WWW-Authenticate`. State-changing POSTs need a valid CSRF token per session and actual config; the `.with(csrf())` utility in MockMvc creates test tokens, not production tokens usable directly with curl.

## 7. Explaining 401, 403, and 302 in Context

### 7.1. Anonymous and Invalid Credentials

With the example's Basic config, when a caller lacks valid authentication and an endpoint requires a role, security handling can forward the anonymous principal's `AccessDeniedException` through `ExceptionTranslationFilter` to `AuthenticationEntryPoint`. The Basic entry point returns **401** with an HTTP challenge. Wrong credentials, meanwhile, are usually handled immediately by `BasicAuthenticationFilter` at the authentication step; the outcome is also **401**, though via a different path.

Do not rely on the rule of thumb "`AuthenticationException` is always 401, `AccessDeniedException` is always 403". The actual status also depends on the entry point, handler, principal type (anonymous/remember-me/full), chain, and which step executes first.

### 7.2. Authenticated but Lacking Permission

`viewer` succeeds at Basic login and carries authority `ROLE_VIEWER`. The `hasAnyRole("ANALYST", "ADMIN")` rule does not match, so the permission check denies and returns 403. Tests must prove **viewer actually authenticated**; otherwise a 401 test only speaks to missing credentials and does not prove that the authorization rule rejects a valid account lacking permission.

### 7.3. Sufficient Permission but Blocked by Another Mechanism

`admin` has the required role for POST but lacks a CSRF token, so it receives 403. This does not contradict the test where admin has permission. To test authorization on a POST, first build a request satisfying other safety preconditions: right HTTP method, content type, CSRF if needed, and valid payload. Only then evaluate the difference between sufficient and insufficient roles.

### 7.4. 302 in Website Login

When a `SecurityFilterChain` uses `formLogin`, unauthenticated requests may be sent to `/login` with 302/303 instead of 401. Website tests should assert the redirect status and appropriate `Location` header; JSON-consuming APIs may require configuring a dedicated entry point to return 401. Do not force all form-login apps to return 401 when the actual design specifies a redirect.

### 7.5. Bearer Tokens

With an OAuth2 Resource Server, missing, invalid, expired tokens or insufficient scopes can produce responses with a Bearer challenge: 401 or 403 depending on error and policy, possibly with `WWW-Authenticate: Bearer ...`. To test authorization by claims/scopes, you can use the `jwt()` or `opaqueToken()` request post-processors; to test cryptographic validation, decoder/introspection, and real failure paths, you need integration tests with the real token validation components. Do not copy `Basic realm` expectations onto Bearer APIs.

## 8. Checking Payload, Headers, and Non-Execution of Business Logic

**Status alone is not enough.** For example, a report-reading endpoint returning 200 with a wrong default payload or another tenant's data still passes `status().isOk()`. For JSON REST APIs, use `jsonPath` to verify IDs, owners, permitted fields, and to assert that sensitive fields **do not exist** in the response. For denied resources, verify the body contains no PII or internal content. Note that 403 may return an error document depending on configuration; avoid locking tests to an empty body unless the contract requires it.

For endpoints with side effects, test that denied requests **do not invoke dangerous operations**. For example, in a service test:

~~~java
// Illustration: service is replaced with @MockitoBean or @MockBean
// matching the Spring Boot version; snippet is not standalone.
mvc.perform(post("/api/admin/publish")
        .with(httpBasic("viewer", "pw"))
        .with(csrf()))
    .andExpect(status().isForbidden());

verify(publishService, never()).publish(any());
~~~

The snippet above uses Mockito and assumes the controller calls `publishService.publish(...)`. In a real app, you can verify the database state remains unchanged after a blocked request; that is stronger than mocking non-invocation when side effects could happen via another path.

Additional useful assertions:

- **Challenge header:** use `header().string(HttpHeaders.WWW_AUTHENTICATE, startsWith("Basic "))` for Basic 401. Avoid hardcoding the realm if the product allows configuring it.
- **Content-Type:** if the API specifies `application/problem+json` or `application/json`, test 401/403 responses against that exact contract.
- **Body leakage:** must not contain tokens, exception stack traces, data objects, passwords, internal roles, or full SQL errors.
- **Redirect:** if using form login, test 302 and `Location`; do not treat every redirect as an error.
- **Idempotency and mutation:** denied requests must not insert/update/delete records or emit success business events.
- **Cache:** responses depending on the principal must not be reused for less-privileged users; verify appropriate `Cache-Control` or cache keys.
- **Auth context:** principal/tenant comes from an authenticated source, never from self-declared query parameters or headers.

## 9. Adding Object-Level Permission Testing

The route rule `hasRole("ANALYST")` only checks the role at the endpoint level. If the URL is `GET /api/reports/{id}` and readers may only view reports **belonging to their own tenant**, record-level authorization checks must be added. Two users both holding `ROLE_ANALYST` can still have different permissions on the same `reportId`.

Extended matrix:

| Principal | Resource | Expectation |
| --- | --- | --- |
| Alice (ANALYST of tenant-A) | Report belonging to tenant-A, granted | 200, tenant-A data only |
| Alice | Report belonging to tenant-B | 403 or 404 per existence-hiding policy |
| Bob (ANALYST of tenant-B) | Report belonging to tenant-B | 200 |
| Viewer of tenant-A | Tenant-A report, missing required role | 403 |
| Anonymous | Any protected report | 401 with Basic |
| Admin | Another tenant's report | Depends on **explicitly defined** cross-tenant permission; never assume global admin has all permissions |

Tests must seed fixtures with explicit owners/tenants, call the same endpoint with different users, and assert real data or non-disclosure of forbidden data. `@PreAuthorize`, custom `AuthorizationManager`s, or service checks can all enforce object-level security, provided every entry point shares the policy and tests target the actual decision point. If 404 is required for objects the user must not know exist, verify this rule consistently across search/list/export, errors, and timing. Never treat a `200` with a masked body as a valid substitute for **denying the entire object**.

## 10. Be Careful with @WithMockUser, user(), and Test Slices

| Tool | What it creates | Suitable for testing | Limitations |
| --- | --- | --- | --- |
| `.with(httpBasic("u", "p"))` | HTTP Basic header | Credentials passing through Basic auth filter + rules | Does not test HTTPS/proxy/network |
| `@WithMockUser(roles = "ANALYST")` | Mock `SecurityContext` with role | Method/HTTP authorization rules | Does not prove passwords/tokens are verified |
| `.with(user("u").roles("ANALYST"))` | Mock principal on request | Individual role scenarios per request | Does not validate real credentials |
| `.with(anonymous())` | Mock anonymous principal | Testing anonymous when suite has a default user | Not an actual request stripped of all real headers |
| `.with(csrf())` | Valid CSRF token in test | POST/PUT/PATCH/DELETE with CSRF | Does not run browser token/cookie issuance flow |
| `.with(csrf().useInvalidToken())` | Invalid CSRF token | CSRF rejection branch | Does not prove browsers enforce same-site protection |

`@WithMockUser` can be a good choice for method security tests:

~~~java
// Illustrative snippet; requires @EnableMethodSecurity,
// a Spring-managed bean, and @PreAuthorize in the application.
@WithMockUser(roles = "ANALYST")
@Test
void analystCanCallSecuredService() {
    assertEquals("ok", securedService.readReport());
}
~~~

However, if the system uses LDAP, SSO, Bearer JWT, or custom password encoders, you need tests going through the real authentication mechanism. A unit test with `user()` will not catch bugs in filter config, decoders, or credential stores.

For `@WebMvcTest`: it tests only an MVC slice—often fast, but you must ensure the chain and required configurations/beans are imported. If a test unexpectedly returns 403 because the default `SecurityFilterChain` differs from production, do not hastily change the expected status; identify which chain is actually loaded. The `@SpringBootTest + @AutoConfigureMockMvc` setup in the example was chosen to keep authn/authz configuration close to the real application.

## 11. Testing by HTTP Method, Matcher, and Filter Chain

**Matcher order:** `authorizeHttpRequests` evaluates rules in order; normally the first matching rule decides. Placing `anyRequest().permitAll()` before `hasRole` will either fail configuration or bypass intended protection. Tests must invoke real URLs and methods, including dynamic paths, URL encoding, and near-duplicate paths.

**GET/POST are not equivalent:** `GET /api/admin/publish` and `POST /api/admin/publish` are completely different, because the example's security rule uses `HttpMethod.POST`. Do not assume a GET test proves a POST endpoint is protected. For applications with `PATCH`, `PUT`, `DELETE`, write corresponding tests and verify CSRF per client mechanism.

**Multiple SecurityFilterChains:** which chain handles a request is chosen by `securityMatcher` and chain ordering. APIs using HTTP Basic or Bearer may need 401; web pages using `formLogin` usually return 302. Test both URIs inside the chain and boundaries across `/api/**`, `/admin/**`, public paths, and unmatched methods. If a route falls into a broader chain, security expectations may change completely.

**Method security:** `@PreAuthorize` requires `@EnableMethodSecurity` and invocation through a proper proxy. An HTTP filter allowing a request does not guarantee the underlying method allows it; tests must observe actual outcomes and exception translation. If a controller calls a service via self-invocation bypassing the proxy, annotation-only tests can miss it.

**CSRF:** enabled by default for unsafe methods in Servlet; role tests must supply a valid token if the product uses CSRF. Do not disable CSRF just to make a POST test easier to run, unless the app's architecture and threat model explicitly decide CSRF is unnecessary for that client/auth mechanism.

**Dispatchers and errors:** `FORWARD`/`ERROR` dispatches, static resources, and error controllers may have separate rules. Secondary 403 errors can mask root errors. With custom error handling, add tests for error paths and verify error routes neither leak data nor accidentally open access.

## 12. Diagnosing Why a Test Fails

| Symptom | Check first |
| --- | --- |
| Anonymous receives 200 on protected endpoint | Is the filter chain enabled for MockMvc? Is the route `permitAll` or a matcher wrong? |
| Anonymous receives 302 instead of 401 | Is there `formLogin`/redirect entry point? Is the test hitting a web page chain? |
| User with right password gets 401 | Credential store, password encoder, username, Basic header, session/token, `SecurityContext` |
| Authorized user gets 403 on GET | Does authority have `ROLE_` prefix? Does matcher match HTTP method/path? Is rule at method/object level? |
| Admin POST gets 403 | CSRF token, auth role, HTTP method, content type, `AccessDeniedHandler` |
| Viewer gets 401 instead of 403 | Are credentials valid? Was `Authentication` lost? Is the user still anonymous? |
| `@WithMockUser` passes but HTTP Basic fails | Mock user test bypassed real authentication; check Basic filter and `UserDetailsService` |
| `@WebMvcTest` does not load expected rules | Check `@Import` of `SecurityFilterChain`, test slice, bean dependencies, auto-configuration |
| 403 returned yet business action executed | Check side effects before authorization, async tasks, filter order, method proxy, and transactions |
| Tests pass but production differs | Proxy/CORS, session cookies, chain order, forwarded headers, tenant context, external identity provider |

Avoid "fixing" by changing `401` to `403` or adding `@WithMockUser` without understanding the root cause. Read Spring Security logs at `DEBUG` level in development to see which filter chain handles the request, how the principal authenticated, and which decision point returned the denial. Do not enable logging of raw credentials or tokens in production.

If a test fails only when running the full suite, examine test isolation: leaked `SecurityContextHolder` or static state between tests, random ordering, mutable in-memory grants, caches, or reused mock beans. Each test should set up its own principal, data, and CSRF; never depend on a previously executed test.

## 13. Test Plan for Security-Critical APIs

A small, meaningful matrix usually beats a huge test suite that only asserts 200:

1. **Public**: anonymous can access only genuinely public routes without bypassing sensitive routes.
2. **Protected + anonymous**: sees no data; response matches auth mechanism (401/challenge or proper redirect).
3. **Protected + authorized**: response has expected status, body, tenant/resource; side effects occur only when allowed.
4. **Protected + unauthorized**: valid credentials but insufficient role/scope/owner; status 403/404 per policy with no information leak.
5. **Bad credentials**: wrong password, expired/revoked token, or invalid signature handled at the authentication boundary.
6. **HTTP mutation**: CSRF valid/invalid/missing per active mechanism; missing permission causes no side effects.
7. **Permission changes**: revoking permission takes effect per permission/token cache lifetime; tests do not assume claims update immediately while old tokens live.
8. **Error/data leak**: error responses return no sensitive data or stack traces; authn/authz audits record proper events when required.
9. **Boundaries**: low-privilege vs high-privilege routes, GET/POST, multiple filter chains, path mismatches, parameter/object/tenant.
10. **Regression**: tests fail if a rule changes from `hasRole` to `permitAll` or matcher order changes, thanks to having both positive and negative cases.

### Checklist Before Finishing

- [ ] Distinguish **unauthenticated**, **authenticated and authorized**, and **authenticated but unauthorized**.
- [ ] Write MockMvc tests passing through the real `SecurityFilterChain` and asserting response status.
- [ ] Verify Basic challenge on 401 in Basic config; understand 302/401/403 depend on entry point and handler.
- [ ] Test right username/password for authentication and right roles/authorities for authorization.
- [ ] Assert both success payload and absence/no side effects on denied branches.
- [ ] For POST, separate CSRF denial from role denial by supplying a valid token in authorization tests.
- [ ] Never treat `@WithMockUser` as proof that real passwords or tokens were authenticated.
- [ ] Extend the matrix for owner, tenant, method-level, multiple chains, and export/error paths when the product requires it.
- [ ] Keep tests isolated, avoid logging passwords/tokens, and never weaken security policy just to make tests pass.

### Official References

- Spring Security — Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring Security — MockMvc Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
