# Reading Migration Guides and Testing Default Behavior Changes in Spring Security

## Learning Objectives

After this lesson, you will be able to: (1) choose the right migration documentation for your source and target versions; (2) distinguish API, configuration, and **default behavior** changes; (3) turn each relevant change into a hypothesis and runnable regression tests; (4) evaluate upgrade results based on the application's actual security rather than merely a successful compilation.

The scope is **how to read guides and verify behavior when upgrading Spring Security**. Examples focus on Spring Security fundamentals, primarily Servlet/Spring MVC applications; for WebFlux, use the corresponding Reactive migration docs and `WebTestClient`.

## 1. Why Read the Migration Guide Even When the Build Is Green?

Upgrading dependencies can leave the application starting cleanly with every controller intact, yet an endpoint flips from allowed to denied, a path stops matching a rule, or the `Location` header on login redirects changes. That is a **security contract change** despite zero compilation errors.

Distinguish three kinds of changes:

| Type | Example | How to detect |
| --- | --- | --- |
| API/source compatibility | Old DSL configuration style removed | Compile, check deprecations, update code |
| Configuration and defaults | Default `RequestMatcher` type changes | Read migration guide, test boundary URLs, compare behavior |
| Runtime/security contract | 401, 403, 302; CSRF; access permissions; sessions/cookies | Integration tests actually traversing the security filter chain |

Do not treat a migration article as a search-and-replace checklist. The most important question is: **after the upgrade, will users/applications sending the same request receive the same permissions, HTTP status, and side effects as before?**

## 2. Identifying the Right Documentation Source and Upgrade Path

1. Record the **currently running** versions of Java, Spring Boot, Spring Framework, Spring Security, `spring-security-test`, and any OAuth2/SAML modules. Prefer the actual dependency tree or BOM over guessing from a single config line.
2. Identify the **target version** and check the corresponding compatibility/support matrix. If using Spring Boot, upgrade along Boot-managed version sets; do not mix incompatible major versions on your own.
3. Open docs for the **exact source branch** (*Preparing for ...* section), then docs for the **target branch** (*Migrating to ...* section). Also read *What's New*, release notes, and changelogs for relevant patches.
4. Pick the right **Servlet** or **Reactive** track. Only dive into Authentication, Authorization, OAuth 2.0, SAML, LDAP, method security, etc. if the application uses them.
5. For each item, confirm whether it describes a change definitely applied, an opt-in preview option, or an API slated for removal; do not assume every branch is affected identically.

**Example 6.x → 7.x upgrade path:** Spring Security documentation recommends using the 6.5 branch to prepare for changes before upgrading to 7.0. The 7.0 guide reminds you to check Spring Boot 4.0 and separate Servlet/Reactive steps. This is an example of one specific upgrade path; projects on other versions must consult the docs matching their exact path.

Note: “Preparing for 7.0” content was written prior to the 7.0 release. Cross-check against current 7.x guides and release notes; do not treat “upcoming change” phrasing in preparation docs as the latest status of an already-released version.

## 3. Turning a Migration Item into a Verification Plan

Read each item using six fixed questions:

1. **Who does this apply to?** Servlet/Reactive, which authentication type, which component, and which URL/method scope?
2. **What differs before and after?** Note the old and new behaviors explicitly; separate documented rules from hypotheses that need confirmation.
3. **What are the trigger conditions?** Default configuration, custom beans, multiple `SecurityFilterChain`s, servlet paths, reverse proxies, sessions, or tokens?
4. **What code or configuration must change?** Replaced APIs, settings that must be declared explicitly, or features that should be opted into first?
5. **What evidence proves safety?** Specific requests, identity/role, HTTP method, URL, CSRF token, expected status/header/body, and write side effects.
6. **If it fails, how should it be handled?** Fix rules/matchers/flows per business intent; use temporary compatibility switches only when documentation permits, backed by tests and a removal plan.

Record template for a change:

| Field | Example content |
| --- | --- |
| Reference | URL to the exact migration page and version |
| Component | `authorizeHttpRequests`, URL `/api/admin/reports` |
| Risk | Matcher changed, request no longer hits the intended rule |
| Contract to preserve | Anonymous denied; USER unauthorized; ADMIN allowed |
| Pre-upgrade test | Three requests with three identities, statuses recorded |
| Post-upgrade test | Re-run the exact three requests, compare and review differences |
| Conclusion | PASS or create a configuration fix task with clear rationale |

Never “accept” a change that widens endpoint access just because a migration guide mentions a new mechanism. The system's authorization intent must still be verified independently.

## 4. Changes Worth Learning to Spot Early

### 4.1. Configuration DSL: Compilation Errors and Behavior Are Two Separate Things

While preparing for Spring Security 7, the docs require **Lambda DSL** instead of the old `.and()` chaining style. Configuration pattern using Lambda DSL:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

This is a **snippet inside a `@Configuration` class** and needs appropriate imports; it is not a standalone runnable Java file. `Customizer.withDefaults()` selects the defaults of the configured module, which does not mean defaults across two major versions are always identical. After updating the DSL so it compiles, you must still test access permissions.

### 4.2. Path Matching Behavior Can Change

The 6.5 → 7 preparation guide notes switching to `PathPatternRequestMatcher` as the default mechanism; older matchers such as `AntPathRequestMatcher` and `MvcRequestMatcher` are no longer the supported path in 7.x. Review both `securityMatcher` (selecting the filter chain) and `requestMatchers` (selecting authorization rules).

Specifically test:

- `/api/admin`, `/api/admin/`, `/api/admin/1`, and paths with encoded characters; do not assume patterns keep identical legacy behavior.
- Requests using `GET`, `POST`, `PUT`, and `DELETE`; rules restricting HTTP methods.
- Applications with multiple Servlets or a servlet path such as `/mvc`. `PathPatternRequestMatcher` takes patterns relative to the **context path**, while servlet prefixes must be accounted for separately where appropriate.
- Rule ordering: specific rules must come before `anyRequest()`; with multiple `SecurityFilterChain`s, check the order and scope of each chain.

For example, with servlet mapping `/mvc`, a controller at `/orders` has the actual URL `/mvc/orders`. Do not assume `/orders` works for every matcher; check `basePath("/mvc")` per the guide and test both allowed and blocked cases.

### 4.3. Login Redirects: URL Contract Changes

The Web Migrations for 7.0 guide states that `LoginUrlAuthenticationEntryPoint` prefers relative paths in `Location` over absolute URLs in the described cases, for example:

~~~http
HTTP/1.1 302 Found
Location: /my-login
~~~

Previously, the application might have seen `Location: https://example.test/my-login`. If the frontend, proxy, or tests compare absolute strings, re-evaluate what the real contract is: does it redirect to the **right login page** without redirecting to an unwanted host? Tests should specify scheme/host/forwarded headers when relevant. Never adjust assertions just to turn tests green when the URL now points somewhere else.

### 4.4. Other Risk Areas Depending on Features Used

| Area | What to check |
| --- | --- |
| Method security | `@PreAuthorize`, `@PostAuthorize`, parameter names used in SpEL; compile with `-parameters` when expressions rely on parameter names |
| Authentication | Login/logout, bad-credential handling, principal/authorities, remember-me, and sessions |
| CSRF | State-changing requests with valid/missing/invalid tokens; CSRF does not vanish on version bumps |
| Exception handling | Unauthenticated: 401 or 302 depending on entry point; authenticated but lacking permission: usually 403 |
| OAuth2/OIDC/JWT/SAML | Redirect/callback flows, issuer/audience/signature, scopes/claims, sessions, and logout if used |
| Serialization | On the 6.5 → 7.0 path, the guide notes moving from Jackson 2 to Jackson 3 integration; check persisted token/session deserialization if used |
| HTTP headers, CORS, cookies, HTTPS | Test critical headers/cookies/redirects against real proxy and browser environments |

These items are a **checklist to cross-reference**, not a claim that every one changes by default in every release. Filter them by the actual changes called out in the documentation for your upgrade path.

## 5. Capturing a Baseline Before Changing Code

A useful baseline includes: commit hash and dependency lock/BOM; `SecurityFilterChain` and method security configurations; endpoint–method–role matrix; session, CSRF, CORS, and exception handling configurations; and existing integration tests. In the test environment, record key HTTP outputs (status, `Location`, `WWW-Authenticate`, `Set-Cookie`, response body, and write side effects). Never record tokens, real passwords, or session IDs in shared logs or artifacts.

**Minimum required matrix** (values are examples for an API using HTTP Basic and CSRF):

| Request | Identity and condition | Expectation |
| --- | --- | --- |
| `GET /public` | Unauthenticated | 200 |
| `GET /private` | Unauthenticated | 401 + HTTP Basic challenge |
| `GET /private` | Valid credentials | 200 |
| `GET /private` | Invalid credentials | 401 |
| `POST /orders` | Authenticated, missing CSRF token | 403 |
| `POST /orders` | Authenticated, valid CSRF token | 201 |
| `GET /admin` | Regular USER | 403 if route requires ADMIN |
| `GET /admin` | ADMIN | 200 if resource exists |

With **form login**, unauthenticated requests to protected URLs usually return **302** to login; with HTTP Basic-only APIs, they usually return **401**. Do not hardcode “every anonymous request always returns 401” or “every unauthorized request always returns 403” without inspecting entry points, filter chains, and HTTP methods.

## 6. Runnable Example: JUnit 5 + MockMvc Verifying HTTP Basic and CSRF

This example intentionally uses **Servlet/Spring MVC and Spring Security Test APIs common across 6.5/7.x**. It is a standalone test class inside an already-configured Spring/Gradle project, requiring no Spring Boot test annotations. Filename: `src/test/java/example/security/MigrationContractTest.java`.

In a **Spring Boot 4.0 + Spring Security 7.x** project with the Boot plugin already applied, declare the dependencies below in `build.gradle` (Groovy). Boot 3.x projects should use the 3.x-line web starter and dependency versions managed by that branch's BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Complete test source code:

~~~java
package example.security;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MigrationContractTest.AppConfig.class)
class MigrationContractTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(springSecurity())
                .build();
    }

    @Test
    void publicRequestIsAllowed() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validCredentialsAllowProtectedGet() throws Exception {
        mvc.perform(get("/private").with(httpBasic("alice", "password")))
                .andExpect(status().isOk())
                .andExpect(content().string("private"));
    }

    @Test
    void invalidCredentialsAreRejected() throws Exception {
        mvc.perform(get("/private").with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void postWithoutCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/orders").with(httpBasic("alice", "password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfTokenIsCreated() throws Exception {
        mvc.perform(post("/orders")
                        .with(httpBasic("alice", "password"))
                        .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("created"));
    }

    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    @Import(DemoController.class)
    static class AppConfig {
        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
            http.authorizeHttpRequests(auth -> auth
                            .requestMatchers("/public").permitAll()
                            .anyRequest().authenticated())
                    .httpBasic(Customizer.withDefaults());
            return http.build();
        }

        @Bean
        UserDetailsService users() {
            return new InMemoryUserDetailsManager(
                    User.withUsername("alice")
                            .password("{noop}password")
                            .roles("USER")
                            .build());
        }
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/private")
        String privateEndpoint() {
            return "private";
        }

        @PostMapping("/orders")
        @ResponseStatus(HttpStatus.CREATED)
        String createOrder() {
            return "created";
        }
    }
}
~~~

Run from the root of the Gradle project:

~~~bash
./gradlew test --tests "example.security.MigrationContractTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.security.MigrationContractTest"
~~~

**Expected result:** 6 tests PASS, Gradle exits with `BUILD SUCCESSFUL`; the requests return statuses 200, 401, 200, 401, 403, 201 respectively in test order. This is the **expected result when run with the stated dependencies and configuration**, not an execution log captured from a specific project.

Explanation of key parts:

- `springSecurity()` attaches Spring Security to `MockMvc`; omitting it can let tests hit the controller without traversing filters, producing a false 200.
- `httpBasic("alice", "password")` adds the HTTP Basic Authorization header, testing **real authentication through the filter**. `@WithMockUser` is useful for isolating authorization checks but does not verify passwords or login protocols.
- `csrf()` generates a valid token for the test request. A `POST` without a token is blocked before reaching the controller; a request with a token is allowed to create the resource.
- `{noop}` in the password is suitable only for test examples with dummy data; real systems must use a secure password encoder.
- When adapting to a real app, replace `DemoController` and `AppConfig` with the real context/config, then expand tests for roles, matchers, sessions, and business endpoints.

## 7. From Documented Changes to Concrete Regression Tests

### Scenario A: URL Matcher Behavior Changes

Suppose the policy is that only ADMIN may read `GET /admin/reports`. Before upgrading, capture results for anonymous/USER/ADMIN; after upgrading, re-run all three. Add boundary cases: `/admin/reports/`, `/admin/reports/2026`, other HTTP methods, and URLs with context/servlet prefixes. A **404** status may mean no handler exists and does not prove the authorization rule is right. To prove authorization, tests should target real endpoints and combine permitted/denied checks.

If a rule fails to match, inspect in order: actual request → chain chosen by `securityMatcher` → matcher in `authorizeHttpRequests` → rule order → controller mapping. Do not immediately add `permitAll()` or disable filters.

### Scenario B: Login Redirect Changes

For apps with `formLogin`, test an anonymous GET to a protected resource and verify the redirect code, destination, and valid host. When a guide notes URLs moving from absolute to relative, any assertion enforcing a full `https://...` string must be checked to see if it truly reflects product requirements. If legacy clients require an absolute URL, configure compatibility using the right version's API and add host/proxy tests; avoid mechanically treating the new default as a security bug.

### Scenario C: Method Security Using Parameter Names

If `@PreAuthorize("@policy.canRead(#id, authentication)")` depends on parameter name `id`, check the `-parameters` compiler flag and test invoking the method as owner vs. non-owner. Passing HTTP tests do not replace method-security tests when logic is guarded at the service layer; verify that the method-security proxy is actually active.

### Scenario D: CSRF and Browser Sessions

For state-changing requests from browsers using cookies/sessions, verify at minimum: no token → blocked; wrong token → blocked; valid token → processed (if authenticated and authorized). Using bearer tokens in headers with stateless config can lead to a different CSRF policy, but that must rest on an actual threat model; **never disable CSRF just to fix a red test**.

## 8. Running the Upgrade Through Small Checkpoints

1. **Baseline:** run tests before changes, record the security policy and critical statuses/headers; know which tests already failed beforehand.
2. **Prepare:** upgrade to the intermediate branch recommended by the migration guide, resolve deprecations, and opt into new behaviors where the docs allow.
3. **Upgrade core:** update Boot/Framework/Security and related starters/modules via dependency management, fixing API and startup issues.
4. **Compare contracts:** re-run the test suite with the **same data, roles, URLs, and profiles**; accept discrepancies only after analysis and confirmation against business requirements.
5. **Integration testing:** test database, reverse proxy, CORS/CSRF, TLS, OAuth/OIDC/SAML IdP, and real browsers if those components exist in the app.
6. **Observe and rollback:** monitor logs for unexpected 401/403/redirects, login loops, or authorization errors; keep a rollback path ready to the prior deployment if serious over-permissioning or false blocks appear.

Prefer running tests in a staging environment matching production in context path, reverse proxy/forwarded headers, session config, and identity provider. A sound MockMvc test is necessary, yet cannot prove every browser or external proxy interaction.

## 9. Diagnosing Red Tests to Their True Root Cause

| Symptom | Where to check first |
| --- | --- |
| Unexpected 200 on a protected endpoint | Is the filter attached to the test? Does `securityMatcher` match the request? Is there an overly broad `permitAll` rule? |
| 401 instead of 200 | Invalid credentials/token, `AuthenticationManager`/provider, entry point, or mocked user/role mismatch |
| 302 instead of 401 | `formLogin`/entry point redirects to login; verify configured flow |
| 403 instead of 200 | Authenticated but lacking privileges, missing CSRF on unsafe method, or method security denial |
| 404 instead of 200 | Controller mapping/context path/servlet path; do not jump to concluding authorization denied it |
| Wrong redirect destination / loop | Relative vs. absolute `Location`, saved request, base URL, and forwarded headers |
| Test PASSES while real app blocks | Test lacks `springSecurity()`, uses mock identity bypassing authentication, lacks proxy/IdP, or uses wrong profile |

Distinguish **expected changes** (documented and accepted by the product), **security regressions** (unintentionally widening access or dropping protection), and **outdated test assumptions** (assertions overly specific about representation that do not reflect product contracts). Update assertions only after classifying them.

## 10. Self-Practice Exercise

Given an application with `/public`, `/orders/**` for USER/ADMIN, and `/admin/**` for ADMIN only, plus form login, choose an appropriate major-version migration guide and:

1. Build a table of at least 8 requests covering anonymous, USER, ADMIN; GET/POST; missing/valid CSRF tokens; URLs with and without a trailing `/`.
2. Cite the exact section in the docs predicting matcher, redirect, or DSL changes; note which items are irrelevant because the app does not use those features.
3. Write tests before upgrading, save results; apply the migration; re-run. If unexpected 403/404/302 results occur, investigate filter chains, matchers, controllers, and entry points before fixing.
4. Write a PASS/FAIL decision: all sensitive endpoints stay blocked for unauthorized roles, login/logout work, state-changing requests enforce CSRF policy, and no unauthorized access is possible.

**Completion criteria:** you can explain *why* each assertion exists, show evidence of before/after behavior, and distinguish fixing code to build from preserving the runtime security contract.

## 11. Checklist Before Merging Changes to Main

- [ ] Verified exact source/target versions, BOM, and Servlet/Reactive track.
- [ ] Read *Preparing*, *Migrating*, *What's New*, and relevant release notes; filtered for features the app actually uses.
- [ ] Recorded a baseline for authentication, authorization, method security, CSRF, redirects, sessions, and matchers.
- [ ] No removed APIs remain; configuration boots cleanly with a compatible dependency set.
- [ ] `spring-security-test` tests traverse the real filter chain where needed; mock identities are not misused to test login.
- [ ] Anonymous/authorized/unauthorized/CSRF/boundary URLs have all been tested.
- [ ] Differences in 401/403/302, headers, and redirect URLs are explained and intentionally accepted.
- [ ] Appropriate environment integration tests and monitoring/rollback mechanisms are ready.

## 12. Official Reference Documentation

- [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Spring Security 6.5 — Preparing for 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html)
- [Configuration Migrations — Lambda DSL](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html)
- [Web Migrations — RequestMatcher and relative redirect](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html)
- [Spring Security — Servlet Testing / MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Boot 4.0 — Build Systems](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html)

When reading online documentation, always select the **version selector** matching your actual dependencies. The 6.5 → 7.0 guide links above illustrate the workflow and do not replace guides for future upgrades.
