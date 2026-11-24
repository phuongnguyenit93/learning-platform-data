# Testing Multiple Filter Chains, Unmatched Endpoints, and Fallback Rules

**Module:** Spring Security – Servlet  
**Parent topic:** HTTP Testing

## 1. The Problem: Why Can a URL Be Protected by a Different Chain Than Expected?

In a Spring Security Servlet application, multiple `SecurityFilterChain` beans can coexist: one chain dedicated to APIs, one chain for admin paths, and one general chain for remaining requests. Each chain has its own matcher, filters, and authorization rules.

For example, an app has:

- `/api/admin/stats`: only users with `ROLE_API_ADMIN` may view.
- `/api/reports`: users with `SCOPE_reports.read` may view.
- `/api/public`: public resource.
- `/web/feedback`: form POST requiring a user with `ROLE_USER` and a valid CSRF token.
- `/shadow`: a controller exists, yet has no allow decision in the security policy.

If the `/api/**` chain has higher priority than `/api/admin/**`, admin requests get processed under the general API policy. If both chains match only a subset of URLs **without a fallback chain**, a request outside all matchers may **not be protected by any Spring Security filter chain**. If you only test familiar endpoints without testing unmatched URLs, this bug may go unnoticed.

**Lesson objectives:**

1. Explain how `FilterChainProxy` selects **the first chain whose `RequestMatcher` matches**.
2. Distinguish **`securityMatcher` selecting a `SecurityFilterChain`** from **`requestMatchers` inside `authorizeHttpRequests` selecting rules for a request already inside the chain**.
3. Configure `@Order` so specialized paths are evaluated before general paths.
4. Place a **`anyRequest().denyAll()`** fallback rule inside each chain and a **catch-all `SecurityFilterChain`** to handle paths outside specialized chains.
5. Use `MockMvc`, `spring-security-test`, `user()`, `csrf()`, and HTTP assertions to test 200 / 401 / 403 boundaries, and avoid false inferences from 404.
6. Detect false positives caused by tests skipping filters, mis-scoped matchers, `web.ignoring()`, duplicate chains, or differing auth/CSRF configs.

**Scope:** Spring Security **Servlet stack** with `HttpSecurity`, not WebFlux `SecurityWebFilterChain`.

## 2. Chain Selection Mechanism: Only the First Matching Chain Applies

Spring Security Servlet uses a `FilterChainProxy` holding an ordered list of `SecurityFilterChain` beans. Each chain has a `RequestMatcher` deciding which requests belong to that chain and a corresponding set of security filters.

~~~text
HTTP request
     |
     v
DelegatingFilterProxy ("springSecurityFilterChain")
     |
     v
FilterChainProxy
     |
     +--> @Order(1)  securityMatcher("/api/admin/**")?
     |      | Yes -> SELECT THIS CHAIN, DO NOT try later chains
     |      | No
     |      v
     +--> @Order(2)  securityMatcher("/api/**")?
     |      | Yes -> SELECT API CHAIN
     |      | No
     |      v
     +--> @Order(3)  no custom securityMatcher?
     |      | Yes -> SELECT FALLBACK CHAIN (matches every request)
     |      v
     +--> No chain matches:
            No Spring Security filters apply to that request
     |
     v
Filters of the selected chain -> DispatcherServlet -> Controller
~~~

**A single request is never processed simultaneously by two `SecurityFilterChain` beans.** The `requestMatchers` inside the second chain **are not evaluated** if the first chain already matched. Thus, a `denyAll` policy in a higher-priority chain can block a request even if a lower-priority chain intended to allow it. That is the desired behavior when order and scope are designed properly.

### 2.1. securityMatcher and requestMatchers Are Two Different Matcher Levels

| Level | API | Responsibility |
| --- | --- | --- |
| **Chain selection** | `http.securityMatcher("/api/**")` | Decides whether a request enters **this `SecurityFilterChain`**. |
| **Authorization inside chain** | `authorizeHttpRequests(auth -> auth.requestMatchers(...).hasAuthority(...))` | Once the chain is selected, applies the matching permission rules. |
| **Fallback inside chain** | `auth.anyRequest().denyAll()` | Denies requests entering the chain that did not match any earlier allow rule. |
| **Fallback across chains** | Final `SecurityFilterChain` bean without custom `securityMatcher` | Ensures all remaining requests are still inspected by Spring Security. |

Within a chain, authorization rules are evaluated **in declaration order**; the first matching matcher decides the policy. Put specialized matchers before general matchers; `anyRequest()` should sit **last**.

**The two "fallback" layers are distinct:**

- `anyRequest().denyAll()` **inside the API chain** applies only to requests **already matched by the API chain**.
- A **catch-all `SecurityFilterChain`** is what covers requests that did not match the API/admin chains.

Having `anyRequest().denyAll()` inside a `securityMatcher("/api/**")` chain **does not protect** `/shadow` outside `/api/**` if no other chain matches it.

### 2.2. Dangerous Configuration Case: No Fallback Chain

~~~java
// UNPROTECTED ILLUSTRATION — DO NOT USE AS-IS IN PRODUCTION.
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

If this is the **only chain**, `/shadow` does not match `/api/**`; `FilterChainProxy` applies no Spring Security filters to that request. If MVC has a `GET /shadow` controller and no other protection layer exists, the route can return data without requiring authentication.

**How to prevent it:** include a final unrestricted chain with explicit `permitAll` for truly public endpoints and `denyAll` for the rest. Never rely on "there is no controller so it will 404"; an endpoint might be added later, or another filter/servlet might handle the request.

## 3. @Order and Overlapping Regions

Suppose:

~~~text
Chain 1: /api/admin/**       (narrow, specialized)
Chain 2: /api/**             (broader)
Chain 3: any request         (catch-all)
~~~

The URL `/api/admin/stats` matches both Chain 1 and Chain 2. Because **Chain 1 is evaluated first**, only Chain 1's policy takes effect.

| URL | Chain to select | Why |
| --- | --- | --- |
| `GET /api/admin/stats` | Chain 1 | Matches `/api/admin/**` first. |
| `GET /api/reports` | Chain 2 | Not under `/api/admin/**`, under `/api/**`. |
| `GET /api/public` | Chain 2 | Has a public permit rule in the API chain. |
| `GET /api/unknown` | Chain 2 | Still under `/api/**`; hits `denyAll` if undeclared. |
| `GET /health` | Chain 3 | Matches neither earlier chain; enters catch-all. |
| `GET /shadow` | Chain 3 | Matches no specialized chain; denied by fallback `denyAll`. |

**Do not** believe that putting `@Order(20)` on a chain makes Spring merge permissions from `@Order(10)` and `@Order(20)`. Order only controls **which chain is evaluated first**.

If two chains share the same order or omit order, selection depends on configuration and actual registration order; never rely on unguaranteed ordering. Use explicit `@Order(1)`, `@Order(2)`, `@Order(3)` and write tests for overlapping paths.

**Do not** set `http.securityMatcher("/api/**")` and assume `requestMatchers("/admin/**")` inside it will capture `/admin/**` outside `/api/**`. Authorization rules do not expand a chain's match scope.

## 4. Designing a Testable Policy

Let us pick a concrete policy:

| Chain | Matcher and @Order | Rules before fallback | Fallback |
| --- | --- | --- | --- |
| **Admin API** | `@Order(1)`, `/api/admin/**` | GET `/api/admin/stats`: `ROLE_API_ADMIN` | `denyAll` |
| **General API** | `@Order(2)`, `/api/**` | GET `/api/public`: public; GET `/api/reports`: `SCOPE_reports.read` | `denyAll` |
| **General fallback** | `@Order(3)`, unrestricted matcher | GET `/`, `/health`: public; POST `/web/feedback`: `ROLE_USER` | `denyAll` |

In this example:

- Uses **HTTP Basic** to test authentication/authorities conveniently with MockMvc; no Identity Provider or database.
- **Keeps default CSRF protection** for state-changing HTTP methods. HTTP Basic in browsers can be auto-sent by the browser, so do not disable CSRF merely because a path starts with `/api`.
- `POST /web/feedback` succeeds only with **the right role and a valid CSRF token**.
- Endpoint `/shadow` exists in MVC yet sits outside the allowlist to prove the fallback truly denies it.
- For pure stateless bearer-token APIs that do not rely on cookies/browser-auto credentials, CSRF policy may differ; evaluate it separately instead of copying `csrf.disable()` from another tutorial.

This is a **fail-closed** design: new paths/methods receive no permissions by default. When opening an endpoint, add a deliberate allow matcher and matching tests.

## 5. Runnable Example: Spring Boot 3.3.5, Java 17, Three SecurityFilterChains

**Requirements:** JDK 17+, Maven, Spring Boot 3.3.5 (to illustrate Spring Security 6.x syntax). Real projects should use supported versions with current security patches.

Structure:

~~~text
multi-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── MultiChainApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/demo/MultiChainSecurityTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-chain-demo</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

`starter-web` provides Spring MVC Servlet, `starter-security` provides security filter infrastructure, `starter-test` provides MockMvc/JUnit/AssertJ, and `spring-security-test` supports mock users and CSRF request processors.

### 5.2. src/main/java/demo/MultiChainApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }
}
~~~

### 5.3. src/main/java/demo/SecurityConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Fixed accounts for local demo only.
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-only"))
                .authorities("SCOPE_reports.read")
                .build(),
            User.withUsername("api-admin")
                .password(encoder.encode("demo-only"))
                .roles("API_ADMIN")
                .build(),
            User.withUsername("web-user")
                .password(encoder.encode("demo-only"))
                .roles("USER")
                .build()
        );
    }

    // Priority 1: narrow chain for /api/admin/**.
    @Bean
    @Order(1)
    SecurityFilterChain adminApiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/admin/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/stats")
                    .hasRole("API_ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Do not blindly disable CSRF for HTTP Basic.
        return http.build();
    }

    // Priority 2: general API chain, does not receive /api/admin/**
    // because the @Order(1) chain already matched admin URLs.
    @Bean
    @Order(2)
    SecurityFilterChain generalApiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Priority 3: no securityMatcher => catch-all.
    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/health")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/web/feedback")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Default CSRF remains enabled for POST /web/feedback.
        return http.build();
    }
}
~~~

**Explaining the tricky points:**

- `@Order(1)` must come before `@Order(2)` because `/api/admin/**` is a subset of `/api/**`.
- In Chain 1, a user with `SCOPE_reports.read` but without `ROLE_API_ADMIN` is still rejected at `/api/admin/stats`. Spring does not fall back to retry Chain 2.
- `requestMatchers(HttpMethod.GET, "/api/reports")` allows **only the GET method** under the defined authority. `POST /api/reports` is not automatically permitted, even if a controller exists.
- `anyRequest().denyAll()` in each chain makes the policy explicit for undeclared paths/methods.
- Chain 3 does **not** call `securityMatcher`; it matches all remaining requests. If Chain 3 were omitted, `/shadow` would no longer be protected by Spring Security.
- `httpBasic()` is chosen to simulate simple authentication. Spring Security Test's `@WithMockUser` or `user()` does not verify real passwords, so an HTTP Basic login integration test is still needed if your project uses that mechanism.
- Do not enable `web.ignoring()` on dynamic endpoints just to skip security, because that **bypasses Spring Security filters** (including helpful headers/filters); `permitAll()` inside the right chain is usually the proper choice for public endpoints.

### 5.4. src/main/java/demo/DemoController.java

~~~java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "home");
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/public")
    Map<String, String> publicApi() {
        return Map.of("resource", "public-api");
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("resource", "reports");
    }

    @GetMapping("/api/admin/stats")
    Map<String, String> adminStats() {
        return Map.of("resource", "admin-stats");
    }

    @PostMapping("/web/feedback")
    Map<String, String> feedback() {
        return Map.of("status", "feedback-received");
    }

    // REAL controller exists, yet fallback denies access.
    @GetMapping("/shadow")
    Map<String, String> shadow() {
        return Map.of("secret", "must-not-be-exposed");
    }
}
~~~

There is no controller for `GET /api/not-configured`. Nevertheless, in this configuration that request matches the API chain, and `anyRequest().denyAll()` is evaluated **before** `DispatcherServlet` checks whether a controller exists.

This matters when writing tests: you may receive **403** instead of **404** for an authenticated user. That is a consequence of security policy blocking the request **before** MVC routing, not proof the endpoint exists.

### 5.5. Manual Run

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Test public endpoints:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/health
~~~

Expected HTTP **200**.

Test an API requiring read permission:

~~~bash
curl -i http://localhost:8080/api/reports

curl -i -u reader:demo-only \
  http://localhost:8080/api/reports
~~~

Expected: first request **401** (unauthenticated), second request **200** when Basic credentials are valid and user holds `SCOPE_reports.read`.

Test admin and an unmatched path:

~~~bash
curl -i -u reader:demo-only \
  http://localhost:8080/api/admin/stats

curl -i -u api-admin:demo-only \
  http://localhost:8080/api/admin/stats

curl -i -u api-admin:demo-only \
  http://localhost:8080/shadow
~~~

Expected: **403**, **200**, **403** respectively. `/shadow` genuinely has a controller, yet is denied by catch-all `denyAll`. Never put demo passwords into operational docs or real shell histories; the commands above are strictly for local learning. Always use HTTPS and secret management for real credentials.

These outcomes are **expected per configuration**, not execution logs observed in the current environment.

## 6. HTTP Testing with MockMvc and spring-security-test

A multi-chain test suite must test **both allowed cases and denied cases**, especially overlapping URLs and unmatched URLs. Testing only `200 OK` on public endpoints is insufficient.

### 6.1. src/test/java/demo/MultiChainSecurityTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MultiChainSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("public-api"));
    }

    @Test
    void protectedApiRejectsAnonymousUser() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void reportScopeAllowsAccessToReports() throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("reports"));
    }

    @Test
    void unrelatedRoleDoesNotGrantReportScope() throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("web-user").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminChainWinsOverOverlappingApiChain() throws Exception {
        // Even with report-reading scope, user lacks ROLE_API_ADMIN.
        mvc.perform(get("/api/admin/stats")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleCanAccessAdminChain() throws Exception {
        mvc.perform(get("/api/admin/stats")
                .with(user("admin").roles("API_ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("admin-stats"));
    }

    @Test
    void unknownAdminPathIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/api/admin/new-operation")
                .with(user("admin").roles("API_ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownApiPathIsDeniedRatherThanFallingThrough() throws Exception {
        mvc.perform(get("/api/not-configured")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedHttpMethodIsDenied() throws Exception {
        // Test token supplied to isolate the rejection cause
        // as the anyRequest denyAll policy rather than missing CSRF.
        mvc.perform(post("/api/reports")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void healthIsPublicThroughFallbackChain() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("up"));
    }

    @Test
    void mappedButUnlistedControllerIsBlockedByFallback()
            throws Exception {
        mvc.perform(get("/shadow")
                .with(user("admin").roles("API_ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void feedbackRequiresCsrfEvenWithCorrectRole() throws Exception {
        mvc.perform(post("/web/feedback")
                .with(user("web-user").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void feedbackRequiresRoleEvenWithCsrf() throws Exception {
        mvc.perform(post("/web/feedback")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_reports.read")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void feedbackWithRoleAndCsrfIsAccepted() throws Exception {
        mvc.perform(post("/web/feedback")
                .with(user("web-user").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("feedback-received"));
    }
}
~~~

**Why use `.with(user(...))`?** It is a `spring-security-test` request post-processor that attaches a test principal and authorities to the request for **authorization integration**. It does not send real Basic credentials and does not prove user details/password encoders work. You can use `httpBasic("reader","demo-only")` in another test to verify the HTTP Basic mechanism end-to-end inside MockMvc.

**Why pass `.with(csrf())` in the `denyAll` POST test?** Without a CSRF token, the request can be rejected **before** `AuthorizationFilter` evaluates `anyRequest().denyAll()`. Adding a valid token lets the test specifically verify that **the rule for undeclared methods** caused the denial. That is variable isolation in security testing.

### 6.2. Running the Tests

~~~bash
mvn test
~~~

Expect **14 tests** to run: public, anonymous, scope, role, chain overlap, unknown path, undeclared method, fallback, and CSRF cases. With the source above, the goal is **0 failures, 0 errors**. This is an **expected outcome**, not an observed execution in the current workspace.

Run only this test class:

~~~bash
mvn -Dtest=MultiChainSecurityTest test
~~~

**A test can pass falsely** if the test setup does not actually wire Spring Security filters. `@SpringBootTest` + `@AutoConfigureMockMvc` in the example uses the full application context along with the app's filter set. If using `MockMvcBuilders.standaloneSetup(...)`, actively integrate Spring Security rather than assuming Spring Security applies automatically.

## 7. How to Prove the Right Chain Was Selected, Not Just Measure HTTP Status

A single status code **does not prove** which chain was selected:

- **401** can come from several different entry points or authentication mechanisms.
- **403** can come from `denyAll`, missing role/scope, bad CSRF token, or resource-level authorization.
- **200** can come from an allowed public endpoint, a test skipping security filters, or an overly broad chain policy.
- **404** can mean MVC found no handler, yet can also be masked by a security policy running before routing.

To verify chain selection, use an **overlapping-paths matrix** and assign distinct policies distinguishable by behavior:

1. `/api/admin/stats` with `SCOPE_reports.read` must be **403**, because the specialized chain requires `ROLE_API_ADMIN`.
2. The same URL with `ROLE_API_ADMIN` must be **200**.
3. `/api/reports` with `SCOPE_reports.read` must be **200**, because it enters the general API chain.
4. `/api/not-configured` with an authenticated user must be **403**, because the API chain matched yet has no allow rule.
5. `/shadow` with an authenticated user must be **403** even though an MVC controller exists, because of catch-all `denyAll`.
6. `/health` anonymous must be **200**, proving the fallback still allows intentionally public endpoints.

When you need finer visibility in development, enable controlled logging/tracing for Spring Security to inspect `FilterChainProxy` and matchers and see which paths are protected. **Never log `Authorization` headers, session cookies, JWTs, or real secrets.**

If you need unit-level checks on chain structure, retrieve `FilterChainProxy` from the Spring context and inspect chains/matchers via APIs supported by your **actual Spring Security version**. Avoid relying solely on log strings or version-internal APIs as your contract test; HTTP behavioral tests remain the primary guarantee.

### 7.1. With Multiple Chains, Filter Counts May Differ

Chain A may have `BasicAuthenticationFilter`, Chain B may have OAuth2 Resource Server filters, and Chain C may have form login/CSRF. Since only **one chain** is selected per request, an endpoint hitting the wrong chain can get the wrong authentication type, different CSRF, different session policy, different security headers, or a different entry point.

Therefore security tests must cover **multiple dimensions**: path, method, anonymous/authenticated, role/scope, CSRF, request headers, and key dispatcher types.

## 8. Unmatched Endpoints: Three Commonly Confused Cases

### 8.1. Unmatched by Controller Yet Matched by SecurityFilterChain

Request `GET /api/not-configured`:

- Matches `securityMatcher("/api/**")`.
- Matches neither `GET /api/public` nor `GET /api/reports`.
- Hits `anyRequest().denyAll()`.
- If authenticated, typically returns **403 before `DispatcherServlet` checks whether a handler exists**.

**Do not write tests expecting 404 by default** for every unmapped MVC endpoint. When security runs ahead of routing, authentication and authorization can block first. To test a true 404, choose a path **permitted by security to reach MVC** that has no handler, or test the MVC layer directly with clear intent. Never open a public path in production just to force 404 if it is not part of the API contract.

### 8.2. Controller Exists Yet Lies Outside Every SecurityFilterChain

Without a catch-all chain, `GET /shadow` can pass through `FilterChainProxy` without any Spring Security filters applied and reach the `/shadow` controller. That is a **coverage gap** if the controller relies entirely on Spring Security.

A test suite calling only `/api/reports` will never catch this. Keep a **canary endpoint that is mapped in MVC yet must be denied**, like `/shadow`, or test a controlled list of out-of-scope endpoints.

### 8.3. Controller Exists and Chain Matches, Yet Lacks Permission

Request `GET /api/admin/stats` with report-reading scope:

- Matches the **admin chain**.
- Path has a real controller.
- User lacks `ROLE_API_ADMIN`.
- Returns **403** when authenticated yet under-privileged.

This is an **authorization failure**, distinct from routing 404 or authentication failure. Do not fix it by adding `permitAll` arbitrarily; adjust role mapping, authentication source, or policy if business requirements genuinely differ.

## 9. How to Choose a Fallback: "Permit or Deny"?

A catch-all chain should usually define explicit rules:

~~~java
@Bean
@Order(999)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/health").permitAll()
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

This is an **alternative illustrative bean**; do not add it alongside section 5's project which already defines `fallbackChain`. Adding two catch-all chains without care causes the higher-priority one to make the lower one unreachable.

**Two common strategies:**

- **Default deny:** `anyRequest().denyAll()`. New endpoints must be explicitly added to an allowlist/role policy. Safe when security boundaries are sensitive and the system is governed by a route inventory.
- **Default authenticated:** `anyRequest().authenticated()`. New endpoints require login, though not necessarily sufficient business permissions. Helpful for web apps where most pages share one baseline policy, yet **does not guarantee role, tenant, or ownership checks**; detailed checks are still mandatory.

**Avoid** `anyRequest().permitAll()` as a general fallback for apps with sensitive endpoints, unless that is genuinely an explicit public contract. It easily introduces vulnerabilities when new routes are added without updating security policy.

If a few endpoints like health or static assets should be public, permit **the exact paths/methods** needed by the business and write tests. Put `denyAll` last to prevent accidental privilege widening.

## 10. SecurityMatcher, Servlet Path, Request Dispatch, and Proxies

### 10.1. Matchers Must Reflect the Actual Path Spring Security Sees

In Servlet apps with a context path, servlet path, multiple `DispatcherServlet`s, or a custom `PathPatternParser`, matchers can behave differently from what you assume looking at browser URLs. With `requestMatchers(String...)`, Spring Security constructs a `RequestMatcher` based on the app environment and version; do not assume everything is a raw string prefix or switch arbitrarily to legacy Ant matchers without testing.

Factors to check:

- **Context path:** a public URL `/myapp/api/reports` does not necessarily mean the security pattern must start with `/myapp`. Verify how the framework evaluates matchers.
- **Servlet path:** with multiple servlet mappings, use matching matchers or `MvcRequestMatcher` configured with `HandlerMappingIntrospector` where applicable.
- **Trailing slashes and path normalization:** `/api`, `/api/`, `/api//reports`, `%2F` encoding, or semicolons can be handled differently across servers/containers. Never build security on manual path normalization.
- **Forwarded headers:** proxies/load balancers must be trusted properly. Never trust `X-Forwarded-*` injected by untrusted Internet clients; those headers affect scheme/host/redirects and must never bypass authentication boundaries.
- **Case sensitivity:** `/API/reports` and `/api/reports` may route differently. Test variants that risk slipping past matchers.
- **New API paths:** an endpoint outside `/api/**` (such as `/v2/reports`) must be protected by the fallback until an explicit rule is added.

**Advice:** test using the actual URLs clients call, rather than guessing from controller names or base paths in source.

### 10.2. DispatcherType: REQUEST, ERROR, FORWARD

An HTTP request can trigger internal dispatches, such as to `/error` when a controller throws, or forwarding to a view. Security filters may be registered for multiple dispatcher types depending on runtime and config; security matching/authorization can apply again on the new dispatch.

Common consequence: a controller is allowed to run, yet when rendering an error, the `ERROR` dispatch to `/error` hits catch-all `denyAll`, turning the final response into 403 or 401 instead of the expected error code. Design error handling appropriately.

One **context-dependent** option is permitting `DispatcherType.ERROR` or a specific error endpoint:

~~~java
// Illustrative snippet inside authorizeHttpRequests:
.dispatcherTypeMatchers(jakarta.servlet.DispatcherType.ERROR).permitAll()
~~~

Apply this only after evaluating why error dispatches are safe and verifying sensitive URLs are not exposed unintentionally. `FORWARD` may also be required for MVC/JSP depending on architecture, yet never permit all forwards blindly to bypass security.

**Do not** treat every 401/403 at `/error` as a missing role on the original endpoint; inspect dispatcher type and dispatch path.

### 10.3. Multiple Filter Chains and Login Entry Points

If a chain has `securityMatcher("/web/**")` and configures `formLogin()`, default `/login` endpoints (GET/POST) may sit **outside that chain's scope**. Then the login flow breaks even though `anyRequest().authenticated()` looks reasonable.

To use form login or logout with a narrow chain:

1. Identify the exact login processing URL, default login page, and logout URL.
2. Ensure those URLs **are matched by the chain holding the related filters**, or bring them into the matching scope.
3. Test GET login, POST login + CSRF, POST logout, and redirects.
4. Prevent a broader higher-priority chain from hijacking another chain's callback/login URLs.

This lesson uses HTTP Basic to avoid designing login pages/sessions across multiple chains. With OAuth2 Login, likewise check that `/oauth2/authorization/{registrationId}` and `/login/oauth2/code/{registrationId}` fall inside the right chain.

## 11. Easy-to-Make MockMvc Test Mistakes

### 11.1. Filters Not Running Yet Returning 200

If you use:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new DemoController())
    .build();
~~~

this is only an illustrative snippet; `standaloneSetup` does not automatically include Spring Security's `FilterChainProxy` like the full `@SpringBootTest` example. `GET /shadow` can return 200 and fool you into thinking security allowed it, when in reality you **did not test security**.

If using standalone MockMvc, provide a security config/filter chain and integrate `springSecurity()`/filters properly, or use `@AutoConfigureMockMvc` with a Spring `ApplicationContext` when testing real HTTP security.

**Do not configure `@AutoConfigureMockMvc(addFilters = false)`** when the goal is verifying the filter chain; it skips the very filters you need to test.

### 11.2. Confusing Mock Users with Real Basic Credentials

~~~java
.with(user("admin").roles("API_ADMIN"))
~~~

creates a test principal. It does not verify `PasswordEncoder` or `BasicAuthenticationFilter` decoding credentials.

To test real HTTP Basic, use the `spring-security-test` helper:

~~~java
// Snippet added inside a test with mvc and in-memory user details:
mvc.perform(get("/api/reports")
        .with(httpBasic("reader", "demo-only")))
    .andExpect(status().isOk());
~~~

Add the static import:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
~~~

This is a snippet inside a test method, not a standalone Java file. In production, never use demo passwords and never send HTTP Basic over non-TLS connections.

### 11.3. Failing to Distinguish CSRF 403 from Authorization 403

With POST and CSRF enabled:

~~~java
mvc.perform(post("/web/feedback")
        .with(user("web-user").roles("USER")))
    .andExpect(status().isForbidden());
~~~

This is a missing-CSRF test. To test permissions, add `.with(csrf())` so the request passes the token check first, and then verifies the role.

If a POST test returns 403 and you forgot `csrf()`, it **does not prove** `hasRole` or `denyAll` is working.

### 11.4. How Do @WithMockUser and .with(user()) Differ?

- `@WithMockUser`: sets the user for the test via Spring TestContext listener; handy when multiple calls in one test share the same principal.
- `.with(user(...))`: attaches a user to **one specific MockMvc request**; very convenient when a single test calls the same URL with multiple roles.

Do not assume a mock principal from a previous request stays "persistently logged in" for the next request. MockMvc tests do not prove real session/login lifecycles unless you explicitly test cookies/sessions and the matching flow.

### 11.5. Testing 200 Is Not Enough; Test Denials Too

A suite must include at minimum: anonymous → 401/redirect; authenticated lacking permission → 403; sufficient permission → 200; undeclared URL → denied; overlapping paths → right chain; POST missing CSRF → 403; valid POST → succeeds.

If you only test positive paths, accidentally changing `anyRequest().denyAll()` to `permitAll()` may **not fail a single existing test**.

## 12. A Systematic Way to Verify Security Coverage

You can maintain an **endpoint matrix** in project documentation without extra dependencies to enforce the principle:

| Group | Typical URL | Method | Anonymous expected | Under-privileged user | Authorized user |
| --- | --- | --- | --- | --- | --- |
| Public API | `/api/public` | GET | 200 | 200 | 200 |
| Scoped API | `/api/reports` | GET | 401 | 403 | 200 |
| Admin API | `/api/admin/stats` | GET | 401 | 403 | 200 |
| Undeclared API endpoint | `/api/not-configured` | GET | 401 | 403 | 403 via `denyAll` |
| Undeclared new method | `/api/reports` | POST + CSRF | 401/403 depending on first filter | 403 | 403 |
| Web action | `/web/feedback` | POST + CSRF | 401/403 depending on first filter | 403 | 200 |
| Public health | `/health` | GET | 200 | 200 | 200 |
| Controller outside allowlist | `/shadow` | GET | 401 | 403 | 403 |

**Note:** HTTP status also depends on entry points and filter order; for POST without a token, `CsrfFilter` may return 403 before authentication runs. Thus the table must state explicitly whether valid CSRF is sent, and tests must isolate conditions when needed. Do not set a rigid expectation "every anonymous request returns 401" across all methods and chains.

### 12.1. Invariant Tests When Adding a New Endpoint

When adding `/api/reports/export`:

1. Identify which chain owns the endpoint.
2. Write a test expecting **denial** before granting policy.
3. Add the right method/scope/role rule if the feature is permitted.
4. Write positive and negative tests for that exact rule.
5. Verify the route does not let a broader matcher swallow a specialized path.
6. For mutation endpoints, test CSRF/threat model and object-level authorization.
7. Run the suite under relevant profiles/reverse-proxy paths/context paths.

Without a fallback chain, tests limited to the API group might miss that `/new-private-path` sits outside security. Keep a coverage canary test using a real mapped controller that is not allowlisted and gets denied.

## 13. Extended Scenarios to Watch

### 13.1. JWT API Chain and Web Session Chain

Real systems often have:

~~~text
@Order(1): /api/** -> Resource Server JWT
@Order(2): /web/** -> form login / session cookie
@Order(3): catch-all -> denyAll
~~~

This is a **diagram**, not deployed code. For APIs using bearer tokens in the `Authorization` header, `JwtAuthenticationConverter` and JWT validators usually determine authorities; for web sessions, roles come from `UserDetailsService` or the login provider.

Test separately:

- Bearer API missing token, bad token, wrong issuer/audience, missing/sufficient scope.
- Web session anonymous, login/logout, CSRF, session fixation, cookie policy.
- Overlapping URLs, login callbacks, Actuator/static/error endpoints not falling outside chains.
- Sending Basic/session credentials to an API meant only for bearer tokens: avoid accidentally enabling a secondary auth mechanism.
- Error/forward dispatch outcomes when multiple chains exist.

### 13.2. A Lower @Order Cannot "Rescue" a Request Denied by a Higher Chain

If Chain 1 matches `/api/admin/stats` and hits `denyAll`, Spring Security **does not continue** to Chain 2 (`/api/**`) looking for `permitAll`. That prevents "keep trying until something permits it" fallback authorization. To allow access, update the rules of **the chain actually selected**, rather than adding rules to a lower-priority chain expecting it to run.

### 13.3. Security Headers, CORS, and Filters Are Not Just Authorization

When a request matches no `SecurityFilterChain`, it loses more than `AuthorizationFilter`; it can also skip filters for **security headers, CSRF, session/context, and authentication**. Custom servlet filters outside `FilterChainProxy` may still run, yet must not be counted as proof Spring Security protected the request.

So never say "the controller needs no auth" just because an unmatched request returned 200. Test coverage and required headers/behaviors explicitly.

### 13.4. @PreAuthorize Does Not Fully Replace the HTTP Chain

Method security helps mitigate risk if an HTTP matcher is missing, yet does not guarantee every controller/service is protected. Unannotated methods, self-invocations bypassing the proxy, or paths skipping the guarded service can remain exposed. HTTP chain matching and method authorization must be tested independently.

## 14. Verification and Debugging Workflow

When an endpoint returns an unexpected outcome:

1. **Confirm the real request**: URL, HTTP method, context path, required headers, dispatcher type; never log secrets.
2. **List all configured `SecurityFilterChain` beans** and `@Order`; find the first chain matching the request.
3. **Check `securityMatcher`** of that chain—do not start by reading only `requestMatchers`.
4. **Check the first matching authorization rule** inside `authorizeHttpRequests`; confirm a `denyAll` fallback or clear policy exists.
5. **Check authentication**: anonymous, authenticated, `ROLE_`/`SCOPE_` authorities, matching token/Basic/session mechanism.
6. **If POST**, check the chain's CSRF token/policy; never confuse CSRF 403 with role 403.
7. **Check MVC routing** only after confirming the request passed security; 404 does not mean a URL is securely protected.
8. **Run overlap tests**: specialized path, general path, path outside both, new method, and under-privileged/authorized users.
9. **Inspect `ERROR`/`FORWARD` dispatches** if the final error code mismatches the original cause.
10. **Verify the real `FilterChainProxy` is present in MockMvc**; never draw conclusions from tests that accidentally dropped filters.
11. **Inspect controlled logs** at the Spring Security/servlet container layer if still unclear; redact or mask tokens/cookies/passwords.
12. **Add a regression test** reproducing the exact path/role/method that triggered the bug before changing policy.

## 15. Common Mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Putting `/api/**` at order 1 and `/api/admin/**` at order 2. | Broad API chain matches first; admin chain is never tried. | Place the narrow chain first and test overlapping paths. |
| Having `anyRequest().denyAll()` in the API chain and thinking all URLs are protected. | It applies only to URLs matched by the API chain. | Add a catch-all `SecurityFilterChain` with no restricting matcher. |
| Configuring `requestMatchers("/admin/**")` inside a chain limited by `securityMatcher("/api/**")`. | Rules do not widen the chain's scope. | Adjust the chain matcher or add a dedicated chain. |
| Using `web.ignoring()` for public dynamic endpoints. | Requests bypass many other Spring Security filters. | Use `permitAll()` in the right chain when appropriate. |
| Omitting `anyRequest` or leaving vague broad policies. | New endpoints/methods lack an explicit contract. | Define explicit rules with `denyAll` fallback per policy. |
| Treating 404 as proof a URL is protected. | 404 belongs to routing and can mask security gaps. | Use a really mapped endpoint + denial test. |
| Treating every 403 as a role error. | CSRF also commonly returns 403. | On POSTs, add `csrf()` in authorization tests. |
| Running `MockMvc` with `addFilters=false`. | Tests do not exercise the security chain. | Enable filters and use Spring Security Test. |
| Using only mock users and claiming Basic/JWT login works. | Real credential/token mechanisms are untested. | Write dedicated authentication integration tests. |
| Setting `anyRequest().permitAll()` in catch-all without review. | New paths can become accidentally public. | Use default deny or `authenticated` per contract. |
| A narrow form-login chain fails to match `/login`. | Login filter/page never handles the URL. | Cover login/logout/callback paths and write tests. |
| Ignoring context path / servlet path / dispatch type. | Matchers differ from browser URLs or error/forward alters outcomes. | Test against the real Servlet environment. |
| Disabling CSRF on a browser HTTP Basic API just because the URL says API. | Browsers can auto-send Basic credentials. | Keep CSRF or evaluate threat model carefully before disabling. |
| Changing status codes without checking chain selection. | Hides symptoms instead of fixing the root matcher/authorization. | Trace the first matching chain and rule. |

## 16. Acceptance Checklist

- [ ] At least one test covers a path inside **two overlapping matchers**.
- [ ] Specialized chains have higher precedence (smaller `@Order` value) than general chains.
- [ ] Every chain ends with an explicit rule for undeclared requests/methods.
- [ ] A catch-all chain covers URLs outside specialized chains.
- [ ] The catch-all uses `denyAll` or an approved default policy.
- [ ] A test covers a **truly mapped controller** denied by the catch-all.
- [ ] Tests cover undeclared API paths and disallowed HTTP methods.
- [ ] Tests cover anonymous → authentication required; under-privileged user → denied; authorized user → 200.
- [ ] For POST/session/browser Basic credentials, CSRF is tested and 403 causes are isolated.
- [ ] MockMvc runs the real filter chain; `addFilters=false` is never used for security tests.
- [ ] Tests do not depend on leftover principals or execution order across cases.
- [ ] Login/logout/OAuth callbacks/error/forward dispatches and context paths are verified if used.
- [ ] `web.ignoring()` is not used as a shortcut to "open permissions" on dynamic endpoints.
- [ ] Authentication and object/tenant authorization are tested beyond URL matchers for sensitive data.
- [ ] Credentials, access tokens, session cookies, or bearer header contents are never logged.

## 17. Self-Check Questions

**Question 1:** A chain has `securityMatcher("/api/**")` and `anyRequest().denyAll()`. Is `/web/admin` protected?

**Answer:** Not automatically. `anyRequest` only applies to requests that entered the `/api/**` chain. If no other chain matches `/web/admin`, the request receives no Spring Security filters. A catch-all chain or a matcher covering that path is required.

**Question 2:** `/api/**` has order 1 and `/api/admin/**` has order 2; which chain handles `/api/admin/stats`?

**Answer:** The `/api/**` chain at order 1 matches first. Spring does not proceed to the admin chain. Reverse the priority so the specialized chain is selected.

**Question 3:** Why can `GET /api/not-configured` return 403 instead of 404?

**Answer:** Because the API chain matches the request and `anyRequest().denyAll()` rejects before `DispatcherServlet` looks for a controller. 403 does not prove an endpoint exists; 404 does not automatically prove an endpoint is protected.

**Question 4:** A POST test returns 403 without a CSRF token. Can we conclude `hasRole` denied it?

**Answer:** Not yet. `CsrfFilter` can return 403 before authorization runs. To test roles, add a valid test token with `csrf()` and vary authorities.

**Question 5:** Why keep a mapped `/shadow` controller that gets denied by the fallback?

**Answer:** It verifies that a fallback chain genuinely covers paths outside specialized chains; if the fallback were removed and the controller became public, the regression test would catch it.

**Question 6:** Do `@WithMockUser` or `.with(user())` verify passwords, Basic authentication, or JWT signatures?

**Answer:** No. They simulate authentication to test authorization. Separate credential/token tests are required when the goal is real authentication.

**Question 7:** Should you always use `anyRequest().permitAll()` as the fallback to avoid confusing 404/403 responses?

**Answer:** No. For systems with sensitive endpoints, that is default-open and easily leaves new routes unprotected. `denyAll` or contract-defined `authenticated` rules are generally safer.

**Question 8:** Why check `/login` when a chain matches only `/web/**`?

**Answer:** Because the login page and login processing URL may sit outside `/web/**`; that chain's form login filter will not handle the request. Cover login/logout/callback paths properly and test them.

---

**Final takeaway:** With multiple `SecurityFilterChain` beans, Spring Security Servlet **uses only the first matching chain**. `securityMatcher` selects the chain; `requestMatchers` selects rules inside the chain; `anyRequest().denyAll()` guards unpermitted requests inside a chain; and a **catch-all chain** guards endpoints outside specialized chains. Proper testing must exercise overlapping paths, new paths, new methods, mapped-but-denied controllers, anonymous/role/scope cases, and CSRF—never conclude safety from a single HTTP status code.