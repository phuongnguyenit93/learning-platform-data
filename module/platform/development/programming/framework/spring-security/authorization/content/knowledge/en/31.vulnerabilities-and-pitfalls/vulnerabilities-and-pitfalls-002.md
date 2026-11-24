# Overly Broad `permitAll` Rules or Rules Shadowed by Matcher Order in Spring Security

An authorization misconfiguration that easily creates a vulnerability is placing `permitAll()` on a pattern that covers sensitive APIs, or writing the right rule that is **never applied** because a broader matcher matched first. The reverse error also occurs: placing a matcher that requires login or denies access before a public matcher causes public endpoints to unexpectedly return 401/403. This lesson explains how Spring Security selects rules, how to define a safe public scope, and how to write tests that catch regressions.

Scope: **Spring Security servlet stack**, configuring `HttpSecurity` with `authorizeHttpRequests` (Spring Security 6.x, Java 17+). The content clearly distinguishes rule ordering **within a single `SecurityFilterChain`** from selection ordering **across multiple filter chains**.

## 1. How Does the Vulnerability Arise?

Suppose an application defines three types of endpoints:

| Endpoint | Desired Policy |
| --- | --- |
| `GET /api/public/ping` | Anyone, including unauthenticated users |
| `GET /api/admin/report` | Only users with the `ADMIN` role |
| `GET /api/orders` | Authenticated users |
| Unlisted URLs | Deny by default |

The following **wrong** configuration looks at first glance like it protects `/api/admin/**`:

~~~java
// WRONG — illustrative fragment, placed inside HttpSecurity configuration.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/orders").authenticated()
    .anyRequest().denyAll()
);
~~~

Actual result:

- `GET /api/public/ping` matches `/api/**` → allowed, as intended.
- `GET /api/admin/report` **also matches `/api/**` first** → allowed even without logging in.
- `GET /api/orders` is also allowed without authentication.
- The `hasRole("ADMIN")` and `authenticated()` rules below are never used for these URLs.

In `authorizeHttpRequests`, Spring Security evaluates matcher/rule pairs in declaration order and applies the **first matching rule**. It does not automatically pick the seemingly “most specific” pattern, does not automatically prioritize `hasRole` over `permitAll`, and does not combine all matching rules.

> **Key takeaway:** A rule that looks strict may still have no effect if it is shadowed by an earlier matcher.

### Fixing Correctly According to the Chosen Policy

~~~java
// RIGHT — expose only the exact endpoint publicly, control the rest in order.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/orders").authenticated()
    .anyRequest().denyAll()
);
~~~

You need to import `org.springframework.http.HttpMethod`. If the application needs multiple public URLs, list them explicitly or group them under a namespace that **cannot** contain sensitive endpoints, such as `/api/public/**` after auditing every URL and HTTP method in that namespace.

In the second example, `GET /api/orders` remains protected because the `/api/orders` matcher stands before `anyRequest()`. Undeclared endpoints will be blocked by `denyAll()`; this approach helps detect newly added controller URLs that were forgotten.

## 2. Two Types of Ordering to Understand Separately

### 2.1. Ordering of Rules Within a Single Chain

Once a request enters a `SecurityFilterChain`, `AuthorizationFilter` applies the list configured via `authorizeHttpRequests`. The policy there is **first match wins**.

| Order | Matcher | Decision |
| --- | --- | --- |
| 1 | `GET /api/public/ping` | `permitAll` |
| 2 | `/api/admin/**` | `hasRole("ADMIN")` |
| 3 | `/api/**` | `authenticated` |
| 4 | `anyRequest()` | `denyAll` |

For `GET /api/admin/report`, the first matcher does not match, the second matcher matches and requires `ROLE_ADMIN`. For `GET /api/private/data`, the third matcher applies. For `GET /ops/health`, none of the three match, so `denyAll` applies.

**Correct scoping order is a necessary condition:** place `/api/**` after the `/api/admin/**` matcher if the two have different protection levels. Avoid maintaining rules after a matcher so broad that they are unreachable.

### 2.2. Selection Order Across Multiple `SecurityFilterChain`s

`FilterChainProxy` iterates through `SecurityFilterChain`s in priority order and picks the **first matching chain** for the request. The `authorizeHttpRequests` rules of unselected chains will **not participate** in the decision.

Mistake example:

~~~java
// WRONG — two Beans illustrating chain ordering, do not copy-paste with other examples.
@Bean
@Order(1)
SecurityFilterChain openEverywhere(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain protectAdmin(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("ADMIN"))
        .build();
}
~~~

`openEverywhere` at order 1 matches `/api/admin/report` as well. The admin-protecting chain at order 2 is not selected. Fix this by placing narrow-scope chains that need special protection first, while building a final chain to control everything remaining:

~~~java
// RIGHT — illustrative Beans when multiple SecurityFilterChains are needed.
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **separate illustrative snippet**, not a complete file. It requires imports for `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, `HttpMethod`, and appropriate application configuration. In these two snippets, `fallbackChain` is not restricted with `securityMatcher`, so it acts as a catch-all chain for all remaining requests.

**`securityMatcher(...)` differs from `requestMatchers(...)`:**

- `http.securityMatcher("/api/**")` determines **which requests are routed into this entire filter chain**.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...))` determines **which authorization rules apply inside the selected chain**.
- `anyRequest()` only means “any request belonging to the current chain that has not yet matched a rule”. It does **not** protect paths that are not selected by any chain.

If no `SecurityFilterChain` matches a URL, that request is not processed by the Spring Security filters in the chain. Therefore, when using multiple chains, you must audit the coverage of all `securityMatcher`s, especially URLs that do not start with `/api/`.

## 3. Identifying Common Misconfigurations

### 3.1. `/api/**` or `/**` Permitted Too Broadly

~~~java
// WRONG: all APIs under /api/ are public.
.requestMatchers("/api/**").permitAll()

// WRONG: a single matcher covering the whole application.
.requestMatchers("/**").permitAll()

// WRONG: every unmatched path is public, including new endpoints.
.anyRequest().permitAll()
~~~

These patterns often come from temporary test configurations, “opening” APIs for the frontend, or adding public endpoints without distinguishing paths. When using `permitAll()`, demand a specific business reason for **each URL and HTTP method**; keep the public surface area to what is strictly necessary.

### 3.2. Public Rule Shadowed by `authenticated` or `denyAll`

~~~java
// WRONG: the first matcher already catches /api/public/ping.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/public/**").permitAll()

// WRONG: the first matcher blocks /api/public/ping.
.requestMatchers("/api/**").denyAll()
.requestMatchers("/api/public/**").permitAll()
~~~

This is usually a functional bug (anonymous users get 401/403 on endpoints meant to be public), but fixing it by switching all of `/api/**` to `permitAll` creates a vulnerability in the rest. The right fix is to **narrow the public matcher** or **move the specific matcher earlier**, then keep the rule protecting the rest.

### 3.3. Forgetting to Constrain the HTTP Method

~~~java
// Check carefully: GET, POST, PUT, DELETE may all be granted access.
.requestMatchers("/api/public/ping").permitAll()

// Narrower: only GET is public.
.requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
~~~

If the same URL supports `GET` to view and `POST` to update, using a method-agnostic matcher can expose write operations publicly. Set policies by method, e.g., `GET` public, `POST` must be authenticated or require a specific authority. Do not use `permitAll` for all `OPTIONS` requests just to hastily “fix CORS”; configure CORS and preflight according to your application's needs.

### 3.4. Similar-Looking or Nested Prefixes

For example, `/api/public/**` is not `/api/publicity`; and `/api/public/admin/**` could sit inside a namespace thought to be public. Do not assume a path name guarantees there are no sensitive functions inside it. When designing routes, cleanly separate public/private areas and add counter-example tests for similar-looking URLs.

Matchers depend on how the application handles servlet path, path pattern, context path, and matching rules of the Spring Security/Spring MVC version. Do not extrapolate a conclusion from one regex/Ant-style pattern to every matcher; test **actual HTTP paths** through `MockMvc` or integration tests. Avoid manually “decoding” or altering URLs before matching without configuration evidence.

### 3.5. Right Rule Placed in the Wrong Chain

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

The `/admin/**` matcher inside the `/api/**` chain does not protect `/admin/dashboard` because that request never enters the chain. If the actual admin endpoint lives at `/api/admin/**`, the matcher inside the chain must also be `/api/admin/**`. Always check **both scoping levels** before concluding a rule is in effect.

### 3.6. Confusing `permitAll` with Disabling All Protections

`permitAll()` only states that the **authorization decision at this matcher** allows access. The request still passes through the selected filter chain, and other mechanisms such as CSRF, custom filters, HTTP security headers, or method security can still affect the outcome.

For example, a `POST` to a `permitAll` endpoint can still receive 403 due to CSRF if the application enables CSRF and the request lacks a token. This does **not** prove whether the matcher worked as intended. Similarly, `web.ignoring()` excludes requests from the Spring Security filter chain and is not equivalent to `permitAll()`; for static resources, the Spring Security documentation recommends `permitAll` so they still receive features like security headers.

## 4. Designing a Safe Policy from the Start

Clarify the list of routes, methods, and permissions before writing matchers. A readable ordering is:

1. **Specific** public endpoints first: login, truly public health checks, static files, approved GETs.
2. Sensitive endpoints by function, role, authority, or policy: `/api/admin/**`, `/api/billing/**`.
3. Broad matchers that **still require protection**: `/api/**` → `authenticated()`.
4. Final rule `anyRequest().denyAll()` to avoid accidentally exposing new endpoints.

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/billing/**").hasAuthority("BILLING_READ")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Four points to check when changing routes:

- Do `/api/admin/**` and `/api/billing/**` sit underneath any earlier broad matcher?
- Does the API **add a new HTTP method** on an old public URL?
- Does changing `securityMatcher`, servlet path, or `@Order` route requests to a different chain?
- Will a new endpoint without its own declaration be blocked or accidentally permitted by a wildcard?

`hasRole("ADMIN")` checks the `ROLE_ADMIN` authority according to the default role prefix. `hasAuthority("BILLING_READ")` requires the exact authority `BILLING_READ`. Do not switch between the two without verifying the mapping from user/JWT to authorities.

**Note on ownership:** `authenticated()` only requires being logged in; it does **not** prove a user is allowed to view every record. For `/api/orders/{id}`, there must be an owner/tenant permission check or service-layer policy to prevent cross-user access. This lesson focuses on matchers and authorization scope; ownership checking is an additional policy layer required when data is sensitive.

## 5. Complete Example: Testing Configuration and Ordering with MockMvc

This example uses **Spring Boot 3.5.7, Spring Security 6.x, Java 17, JUnit 5**. No real server startup or database connection is needed. Create the project:

~~~text
permit-all-order-demo/
├── pom.xml
└── src/test/java/com/example/security/MatcherOrderTest.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>permit-all-order-demo</artifactId>
    <version>1.0.0</version>
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
</project>
~~~

### 5.2. `MatcherOrderTest.java`

~~~java
package com.example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = MatcherOrderTest.TestApp.class)
@AutoConfigureMockMvc
class MatcherOrderTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({RulesConfig.class, DemoController.class})
    static class TestApp {}

    @Configuration(proxyBeanMethods = false)
    @EnableWebSecurity
    static class RulesConfig {

        @Bean
        SecurityFilterChain appChain(HttpSecurity http) throws Exception {
            http.authorizeHttpRequests(auth -> auth
                    // Only the GET method on a single endpoint is public.
                    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
                    // Control the admin area before the broader API matcher.
                    .requestMatchers("/api/admin/**").hasRole("ADMIN")
                    // All remaining APIs require authentication.
                    .requestMatchers("/api/**").authenticated()
                    // Block URLs not declared in the policy.
                    .anyRequest().denyAll()
                )
                // Use HTTP Basic for consistent 401 testing.
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable);
            return http.build();
        }
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/public/ping")
        String ping() { return "pong"; }

        @PostMapping("/api/public/ping")
        String createPing() { return "created"; }

        @GetMapping("/api/admin/report")
        String adminReport() { return "restricted"; }

        @GetMapping("/api/private/data")
        String privateData() { return "private"; }

        @GetMapping("/api/publicity")
        String nearbyNameButPrivate() { return "sensitive"; }

        @GetMapping("/ops/health")
        String operationsHealth() { return "internal"; }
    }

    @Autowired
    MockMvc mvc; // AutoConfigureMockMvc applies Spring Security filters.

    @Test
    void anonymousCanReadDeclaredPublicGet() throws Exception {
        mvc.perform(get("/api/public/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadPrivateApi() throws Exception {
        mvc.perform(get("/api/private/data"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotReadAdminApi() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void authenticatedUserCanReadPrivateApi() throws Exception {
        mvc.perform(get("/api/private/data"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void authenticatedUserCannotReadAdminApi() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAdminApi() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isOk())
           .andExpect(content().string("restricted"));
    }

    @Test
    void similarLookingPathIsNotAccidentallyPublic() throws Exception {
        mvc.perform(get("/api/publicity"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void postOnGetOnlyPublicPathRequiresLogin() throws Exception {
        mvc.perform(post("/api/public/ping").with(csrf()))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void authenticatedPostWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/api/public/ping").with(csrf()))
           .andExpect(status().isOk())
           .andExpect(content().string("created"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void unrelatedAreaIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/ops/health"))
           .andExpect(status().isForbidden());
    }
}
~~~

Run from the project root directory with JDK 17+ and Maven:

~~~bash
mvn test
~~~

**Expectation:** Maven runs 10 JUnit 5 tests and reports success. Log output and duration depend on the environment; what matters is that every `status()` and `content()` assertion passes.

**Testing note:** The example enables `.httpBasic(...)` and disables form login so unauthenticated cases receive HTTP 401 instead of a redirect to a login page. Specific 401/403 behavior may differ in applications using OAuth2 login, Bearer tokens, or custom exception handling; test according to your application's API.

The `postOnGetOnlyPublicPathRequiresLogin` test intentionally adds `.with(csrf())`. Without the token, `CsrfFilter` could reject POST before the authorization step; a test returning 403 then **does not prove** whether `permitAll` applies to POST or not. When testing URL policy, you must control other filter conditions to draw the right conclusion.

`@WithMockUser` mocks identity and authorities for authorization testing; it does not mean real login mechanisms or JWT validation have been tested. The final test calls a URL **backed by a real controller** that is blocked by `anyRequest().denyAll()`, avoiding confusing a 404 from having no handler with an access-denied policy.

### 5.3. Verifying That Tests Catch Real Bugs

Try replacing only the rules in `RulesConfig` of the example above with the wrong configuration:

~~~java
// WRONG: used temporarily to prove regression tests catch the bug.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Do not keep this change in real code. The tests expecting 401/403 for `/api/admin/report`, `/api/private/data`, `/api/publicity`, or POST will fail: the `/api/**` rule turned those paths public. This is an essential signal to catch the vulnerability **before deploying the configuration to production**.

Try the reverse error:

~~~java
// WRONG: a broader rule shadows the public rule below it.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
    .anyRequest().denyAll()
);
~~~

The `anonymousCanReadDeclaredPublicGet` test will no longer receive 200: the `/api/**` matcher requires authentication before `permitAll` is evaluated. Both experiments show that **position in the list** is part of the policy, not just the matcher name.

## 6. Required Regression Test Matrix

The following table assumes the **safe configuration** from Section 5 with HTTP Basic and the declared routes:

| Actor | Request | Selected Rule | Expected HTTP |
| --- | --- | --- | --- |
| Anonymous | `GET /api/public/ping` | Specific public GET | 200 |
| Anonymous | `GET /api/private/data` | `/api/** → authenticated` | 401 |
| User with `ROLE_USER` | `GET /api/private/data` | `/api/** → authenticated` | 200 |
| Anonymous | `GET /api/admin/report` | `/api/admin/** → hasRole` | 401 |
| User with `ROLE_USER` | `GET /api/admin/report` | `/api/admin/** → hasRole` | 403 |
| User with `ROLE_ADMIN` | `GET /api/admin/report` | `/api/admin/** → hasRole` | 200 |
| Anonymous | `GET /api/publicity` | `/api/** → authenticated` | 401 |
| Anonymous, with CSRF | `POST /api/public/ping` | `/api/** → authenticated` | 401 |
| User with `ROLE_USER`, with CSRF | `POST /api/public/ping` | `/api/** → authenticated` | 200 |
| User with `ROLE_ADMIN` | `GET /ops/health` | `anyRequest → denyAll` | 403 |

Do not test only **allowed** URLs. A `GET /api/admin/report` returning 200 with role `ADMIN` does not prove ordinary users **cannot** call it. Unauthenticated cases and authenticated-without-permission cases are mandatory.

With multiple `SecurityFilterChain`s, add test cases for chain boundaries: paths belonging to the admin chain, paths near the admin prefix that belong to the fallback chain, URLs outside `/api`, and newly added URLs. If one chain is shadowed by another matcher, at least one test using an unauthorized user must catch it.

## 7. Review and Remediation Workflow in Real Projects

### Step 1. List the Scope of All Chains

Find beans returning `SecurityFilterChain`, paying attention to `@Order`, `securityMatcher(...)`, and default chains. Draw a table: “sample request → first matching chain”. If no chain matches, that is a gap that must be fixed.

### Step 2. Read Matchers Inside Each Chain Top-to-Bottom

For each chain, list the `requestMatchers` and `anyRequest` policies. Specifically check whether a matcher like `/**`, `/api/**`, `/public/**`, or `anyRequest` shadows rules below it. Do not rely on class placement, bean names, code formatting, or the IDE still displaying the rule to conclude it is executed.

### Step 3. Cross-Reference Real Endpoints

Build an inventory from controller mappings, API gateway/reverse proxy, HTTP methods, servlet path, and context path. Watch for new endpoints or new methods sharing a URL with a public GET. If a proxy rewrites paths, check the actual request URI received by the application.

### Step 4. Make Minimal Fixes, Maintain Deny-by-Default

Narrow overly broad `permitAll` rules, move sensitive matchers ahead of generic ones, or adjust `securityMatcher`/`@Order` so the right chain receives the request. Put `anyRequest().denyAll()` on the remaining catch-all chain if appropriate for product policy. When making changes, avoid temporarily opening all of `/api/**` to diagnose frontend errors.

### Step 5. Run Positive and Negative Tests

Run `MockMvc`/integration tests for **anonymous, regular user, and privileged user** on the same endpoint; differentiate GET/POST; for write requests, supply valid CSRF if CSRF is enabled. Test similar-looking paths, overlapping chains, undeclared endpoints, and accessing another user's resources. Specifically verify sensitive URLs are not captured by an earlier public rule.

### Step 6. Read Logs to Verify Routing

When troubleshooting, you can enable scoped logging in a test environment:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Logs help identify which filter chain is being applied and how security processes the request. Log format varies by version and log level; it does not replace HTTP behavior tests. Avoid enabling overly broad sensitive logging in production.

## 8. Pitfalls When Interpreting Results

**An endpoint returning 403 is not necessarily from `authorizeHttpRequests`.** For POST/PUT/DELETE, first check CSRF and CORS/custom filters. Use a valid request to test permission policy; then test CSRF separately.

**An endpoint returning 404 does not prove it is protected.** If the route does not exist, a request can end in 404 even when authorization defaults to public; when testing permissions, use a route with a real controller or a spy verifying the controller does not run when denied.

**Login is a necessary condition, but may not be sufficient.** `authenticated()` allows any authenticated user; resources by ID, tenant scope, and privileged functions require object/role authorization. Namespace-protecting matchers do not solve IDOR/BOLA on their own.

**`permitAll` does not mean bypassing all authentication and protection.** The selected filter chain can still run. Keep the security filter chain for static resources rather than excluding them with `web.ignoring()` if you simply want everyone to access them.

**Matcher order is not controller endpoint order.** Moving `@GetMapping` in Java source will not fix an incorrect `requestMatchers` list. Order is determined in security configuration, and across multiple chains also depends on `@Order` + `securityMatcher`.

**Do not overlook other HTTP methods.** If only GET is public, do not use a method-less matcher for the same URL and assume POST will be safe thanks to CSRF. CSRF has its own configuration and exceptions; authorization must be right even when the request has a valid CSRF token.

**Migrating from `authorizeRequests` to `authorizeHttpRequests` may require reviewing old matcher configs.** Do not copy patterns verbatim from the old API while ignoring changes in matcher selection across versions. Test actual paths, methods, and filter-chain coverage after upgrading.

## 9. Pre-Deployment Review Checklist

- [ ] Every `permitAll` endpoint has a clear business reason and minimal URL/method scope.
- [ ] No `/api/**`, `/**`, or `anyRequest().permitAll()` accidentally covers sensitive endpoints.
- [ ] Specific matchers with higher protection stand **before** broader matchers in the same chain.
- [ ] No required rule is shadowed by an earlier matcher.
- [ ] With multiple chains, `@Order` and `securityMatcher` route requests to the intended chain.
- [ ] A suitable fallback chain protects or denies remaining paths; no gaps exist outside all chains.
- [ ] Checked GET/POST/PUT/DELETE when the same URL handles multiple operations.
- [ ] Anonymous and authenticated-without-authority tests exist for every sensitive endpoint.
- [ ] Tests confirm public routes are truly public, private routes are truly private, and similar URLs are not exposed by mistake.
- [ ] POST tests use valid CSRF when testing authorization, avoiding confusion over the 403 cause.
- [ ] For owner/tenant-scoped data, policies exist at the appropriate layer beyond HTTP namespace checks.
- [ ] After matcher or framework version changes, rerun the full authorization regression suite.

## 10. Official References

- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Java Configuration, multiple `SecurityFilterChain`: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Architecture, `FilterChainProxy`: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — Setting Up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html

**Acceptance Criteria:** For `GET /api/admin/report`, regular users must be blocked even when a public rule is nearby; for `GET /api/public/ping`, anonymous access must succeed; for `POST` on the same URL, anonymous users must still be required to log in if only GET is public. These tests must be preserved when adding endpoints, changing paths, modifying `@Order`, or upgrading Spring Security.
