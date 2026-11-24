# Writing Tests That Prove New Endpoints Are Never Missed

## 1. Problem: Adding an Endpoint Adds an Access Surface

Suppose a system already has APIs to read and create documents. A few weeks later, a developer adds `GET /api/reports/export` to export reports. The controller method may run right away, yet **who is allowed to call that endpoint** remains a security decision that must be reviewed.

There are at least three failure modes:

1. **A new endpoint is unintentionally left open:** the configuration has an overly broad rule like `/api/**.permitAll()` or `anyRequest().authenticated()`, allowing users with insufficient permissions to access it.
2. **A new endpoint is blocked without anyone noticing:** `anyRequest().denyAll()` provides fail-closed defaults, yet a new feature may return `403` in production because the developer forgot to declare its policy. A safe fallback alone does not prove every endpoint has been reviewed.
3. **Tests give a false sense of security:** requests to a URL without a controller return `404`, or missing CSRF tokens return `403` before authority checks even run. A test that asserts only a status code without verifying the route and cause can miss real bugs.

This exercise combines **two assurance layers with distinct goals**:

- **Default deny (fail closed):** any HTTP request without an explicit policy hits `denyAll()`.
- **Endpoint inventory (route coverage):** automated tests inspect the MVC routes actually registered by Spring and compare them against the list of routes with reviewed permissions. Adding a route while forgetting to review its policy causes the test to **turn red immediately in CI**.

Next, write behavioral authorization tests for the new endpoint itself: unauthenticated guests receive `401`, accounts without the permission receive `403`, and accounts with the permission receive `200`. The exercise asks not only "is the endpoint blocked?" but also "does the endpoint have the right, verifiable policy?".

**Implementation scope:** Spring Boot 3.5.x, Java 17+, Spring MVC/Servlet, and Spring Security 6.x; all accounts and data are learning examples. If a project uses WebFlux, apply the corresponding router inventory and `WebTestClient` tests rather than copying MVC code mechanically.

## 2. Designing the Permission Matrix Before Creating the Route

The demo application has three users:

| Account | Authority | Purpose |
| --- | --- | --- |
| `alice` | `document:read` | Read documents only |
| `bob` | `document:read`, `document:write` | Read and create documents |
| `eva` | `report:export` | Export reports only |

The **new route** is `GET /api/reports/export` and requires `report:export` specifically. `bob` has permission to write documents but **does not** have permission to export reports; there is no implicit inheritance between distinct authorities.

| HTTP route | Anonymous | `alice` | `bob` | `eva` |
| --- | --- | --- | --- | --- |
| `GET /public/ping` | `200` | `200` | `200` | `200` |
| `GET /api/documents/42` | `401` | `200` | `200` | `403` |
| `POST /api/documents`, with valid CSRF | `401` | `403` | `201` | `403` |
| **`GET /api/reports/export` (new)** | **`401`** | **`403`** | **`403`** | **`200`** |
| `GET /api/unknown` | Blocked | `403` | `403` | `403` |
| `POST /api/reports/export`, with valid CSRF | Blocked | `403` | `403` | `403` |

In the last two rows, "Blocked" may appear as `401`/`403` depending on entry point, method, and security setup. The test suite primarily checks **authenticated** users to verify the `denyAll` rule. Because the example uses HTTP Basic, unauthenticated GET requests to protected endpoints receive `401`. Logged-in POST requests must carry a valid CSRF token so `403` reflects **permission**, rather than CSRF rejection beforehand.

Name each policy category: `PUBLIC` (open to everyone), `DOC_READ`, `DOC_WRITE`, and `REPORT_EXPORT`. The list of routes paired with these policies is the **reviewed inventory**, and must not be auto-generated from controllers; auto-generating it would strip the coverage comparison of its ability to catch new routes.

## 3. Project Structure and Dependencies

Initialize a Java 17+, Spring Boot 3.5.x project with **Spring Web (MVC)** and **Spring Security**. In the Spring Boot skeleton's `build.gradle`, ensure these dependencies are present:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is just the `dependencies` and `tasks` block from a Spring Initializr project, not the entire `build.gradle`. The example uses package `com.example.routeaudit` and two files:

- `src/main/java/com/example/routeaudit/RouteAuditApplication.java` — application, reviewed route inventory, Security config, and controller.
- `src/test/java/com/example/routeaudit/RouteAuditApplicationTests.java` — tests comparing the inventory against live mappings and the access matrix.

Here all helper classes inside the main Java file are **package-private**; only `RouteAuditApplication` is `public`. That lets them live in a single Java file while remaining accessible to tests in the same package.

## 4. Application Code: Policy Inventory, Deny-All, and New Endpoint

File `src/main/java/com/example/routeaudit/RouteAuditApplication.java`:

~~~java
package com.example.routeaudit;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RouteAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(RouteAuditApplication.class, args);
    }
}

// Route identifier: HTTP method and path pattern must match.
record RouteKey(HttpMethod method, String path) {}

enum PermissionRule {
    PUBLIC, DOC_READ, DOC_WRITE, REPORT_EXPORT
}

record RoutePolicy(RouteKey route, PermissionRule rule) {}

// Updated only after permission review; never generated from controllers.
final class ReviewedEndpointPolicies {
    private ReviewedEndpointPolicies() {}

    static final List<RoutePolicy> ALL = List.of(
        new RoutePolicy(
            new RouteKey(HttpMethod.GET, "/public/ping"),
            PermissionRule.PUBLIC),
        new RoutePolicy(
            new RouteKey(HttpMethod.GET, "/api/documents/{id}"),
            PermissionRule.DOC_READ),
        new RoutePolicy(
            new RouteKey(HttpMethod.POST, "/api/documents"),
            PermissionRule.DOC_WRITE),
        // New route with explicitly assigned permission:
        new RoutePolicy(
            new RouteKey(HttpMethod.GET, "/api/reports/export"),
            PermissionRule.REPORT_EXPORT)
    );

    static Set<RouteKey> keys() {
        return ALL.stream()
            .map(RoutePolicy::route)
            .collect(Collectors.toUnmodifiableSet());
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("document:read")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities("document:read", "document:write")
                .build(),
            User.withUsername("eva")
                .password(encoder.encode("eva-pass"))
                .authorities("report:export")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> {
            // Every rule is driven by the reviewed inventory.
            for (RoutePolicy policy : ReviewedEndpointPolicies.ALL) {
                RouteKey route = policy.route();
                var match = auth.requestMatchers(
                    route.method(), route.path());

                switch (policy.rule()) {
                    case PUBLIC -> match.permitAll();
                    case DOC_READ ->
                        match.hasAuthority("document:read");
                    case DOC_WRITE ->
                        match.hasAuthority("document:write");
                    case REPORT_EXPORT ->
                        match.hasAuthority("report:export");
                }
            }

            // No policy: never allowed through.
            auth.anyRequest().denyAll();
        });

        // Demo HTTP Basic; default CSRF protection remains active.
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}

@RestController
class ApiController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{id}")
    String readDocument(@PathVariable("id") long id) {
        return "document:" + id;
    }

    @PostMapping("/api/documents")
    @ResponseStatus(HttpStatus.CREATED)
    String createDocument(@RequestParam("title") String title) {
        return "created:" + title;
    }

    // Endpoint added after the three existing endpoints.
    @GetMapping("/api/reports/export")
    String exportReport() {
        return "report-exported";
    }
}
~~~

### Why does this pattern provide two layers of assurance?

**First, every route has an explicit policy.** `ReviewedEndpointPolicies.ALL` records both the HTTP method and the path pattern. Inside `SecurityFilterChain`, each entry becomes the exact matcher and authority requirement. `GET /api/reports/export` accepts only `report:export`; `bob` is not treated as an "admin" just for having `document:write`.

**Second, the fallback blocks everything else.** `anyRequest().denyAll()` sits at the end of the rule list, so a new endpoint not yet added to the inventory cannot be opened merely by being logged in. We deliberately choose **one filter chain covering the entire MVC app**: for instance, we do not restrict the chain with `securityMatcher("/api/something/**")`, because narrowing chain scope can leave another route unprotected if no fallback chain exists.

**Third, the inventory is an independent input from controllers.** If someone adds `@GetMapping("/api/internal/debug")` to `ApiController` without adding a corresponding `RoutePolicy`, the route is still registered by Spring MVC. At that point:

- At runtime, `anyRequest().denyAll()` denies requests to the newly created route.
- In development, the **mapping inventory test** in the next section detects the new route in MVC missing from `ReviewedEndpointPolicies.ALL`, fails, and forces the author to define a policy.

Testing only that `/api/unknown` returns `403` proves only **the fallback**, not that all controller routes have been reviewed. That is why both types of tests are needed.

### Details to understand before testing

- `HttpMethod.GET` and `HttpMethod.POST` are part of the route key: a POST to a path permitted only for GET must be rejected.
- `@GetMapping` and `@PostMapping` register real routes in Spring MVC; in this exercise there are four routes and four `RoutePolicy` entries.
- In-memory passwords serve only this exercise. `PasswordEncoderFactories` encodes them before storing, yet the sample passwords still sit in source code; real apps must use proper identity stores and secret management.
- `GET` requires no CSRF token by default; `POST` generally requires a token. Valid POST tests use `csrf()` so authority checks are not conflated with CSRF errors.
- Routes return static strings so both **status** and **body** can be asserted. Returning `200`/`201` does not mean data was persisted to a database.

## 5. Writing Tests: Automatically Detecting Every New MVC Mapping

File `src/test/java/com/example/routeaudit/RouteAuditApplicationTests.java`:

~~~java
package com.example.routeaudit;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import static org.assertj.core.api.Assertions.assertThat;
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
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RouteAuditApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    RequestMappingHandlerMapping handlerMapping;

    @Test
    void everyApplicationRouteHasExplicitReviewedPolicy() {
        // Check only controllers in the demo package;
        // exclude /error and internal framework endpoints.
        var mappings = handlerMapping.getHandlerMethods()
            .entrySet().stream()
            .filter(entry -> entry.getValue().getBeanType()
                .getPackageName().equals("com.example.routeaudit"))
            .toList();

        assertThat(mappings).isNotEmpty();

        // Forbid @RequestMapping without an explicit HTTP method.
        for (var entry : mappings) {
            RequestMappingInfo info = entry.getKey();
            assertThat(info.getMethodsCondition().getMethods())
                .as("HTTP method not specified: %s", entry.getValue())
                .isNotEmpty();

            assertThat(info.getPatternValues())
                .as("Path not specified: %s", entry.getValue())
                .isNotEmpty();
        }

        // Collect (method, path) directly from Spring MVC mappings.
        Set<RouteKey> registered = mappings.stream()
            .flatMap(entry -> entry.getKey()
                .getPatternValues().stream()
                .flatMap(path -> entry.getKey()
                    .getMethodsCondition().getMethods().stream()
                    .map(method -> new RouteKey(
                        HttpMethod.valueOf(method.name()), path))))
            .collect(Collectors.toSet());

        // Prevent duplicate keys in the policy inventory.
        assertThat(ReviewedEndpointPolicies.keys())
            .hasSize(ReviewedEndpointPolicies.ALL.size());

        // Adding a route without declaring a policy => test FAILS.
        // Declaring a policy while forgetting the controller => also FAILS.
        assertThat(registered).containsExactlyInAnyOrderElementsOf(
            ReviewedEndpointPolicies.keys());
    }

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void documentReadStillChecksItsOwnAuthority()
            throws Exception {
        mvc.perform(get("/api/documents/42"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/documents/42")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:42"));

        mvc.perform(get("/api/documents/42")
                .with(httpBasic("eva", "eva-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void documentWriteNeedsAuthorityAndCsrf()
            throws Exception {
        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("alice", "alice-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:Note"));

        mvc.perform(post("/api/documents")
                .param("title", "Note")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void newlyAddedExportHasItsOwnPermission()
            throws Exception {
        mvc.perform(get("/api/reports/export"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports/export")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/export")
                .with(httpBasic("bob", "bob-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/export")
                .with(httpBasic("eva", "eva-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-exported"));
    }

    @Test
    void unlistedPathsAndMethodsAreDenied()
            throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("eva", "eva-pass")))
            .andExpect(status().isForbidden());

        // POST to a URL with only a GET policy must not get through.
        // Provide CSRF to rule out failure from missing CSRF.
        mvc.perform(post("/api/reports/export")
                .with(httpBasic("eva", "eva-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
~~~

### Why is the route-inventory test important?

`handlerMapping.getHandlerMethods()` returns the MVC mappings **registered by Spring in the real application context**. We filter controllers by the demo package to avoid counting `/error` or internal framework mappings. Every mapping must declare an explicit HTTP method; if a method uses plain `@RequestMapping("/api/example")` without specifying a method, the test proactively **fails** instead of silently skipping it.

Next, the test builds the set of `(HttpMethod, path)` keys from `getPatternValues()` and `getMethodsCondition().getMethods()` and compares it against `ReviewedEndpointPolicies.keys()`. The two sets must be **equal**:

- **Registered but not reviewed:** a new endpoint exists that has not been classified or intentionally exposed.
- **Reviewed but not registered:** a policy exists for a nonexistent endpoint, or the endpoint URL changed without updating the inventory.
- **Duplicate route in the inventory:** the size of `ALL` differs from the number of distinct keys, so the check fails.

This test is not merely echoing back the list of routes we defined ourselves: **the left side is truth from Spring MVC; the right side is the policy list maintained intentionally by developers**. That independent comparison catches missed endpoints.

### Why is MockMvc still needed?

Inventory checks only verify that every route has **a declared policy**; they do not prove the policy picks the right authority or that matchers actually block the right callers. `MockMvc` executes requests through the Spring Security filter chain into MVC, verifying behavior independently:

- Anonymous calling `GET /api/reports/export` → `401`.
- `alice` has `document:read` and `bob` has `document:write`, yet both lack `report:export` → `403`.
- `eva` has `report:export` → `200` with body `report-exported`.
- `eva` cannot POST to the report export path → `403` when the request includes a CSRF token, proving **HTTP methods** are covered too.
- An authenticated user calling `GET /api/unknown` → `403` due to the fallback.

When an endpoint passes the security chain without a matching controller, the request can return `404`. Therefore **testing 403 on an arbitrary URL does not prove the new route itself exists**. Combining the Spring MVC inventory test with body assertions on the new endpoint removes that ambiguity.

## 6. Running Tests and Performing Red–Green Experiments

In the initialized Gradle project directory, run:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows PowerShell use `.\gradlew.bat test`, then `.\gradlew.bat bootRun` if you want to make live HTTP calls. `test` boots its own test context and requires no external server running.

**Expected result:** all **six test methods** pass with the original configuration. Run logs vary by machine; do not expect fixed timings or log line counts.

### Experiment A — Adding a new endpoint while forgetting its policy

Add the following method to `ApiController` (in the same application):

~~~java
@GetMapping("/api/internal/debug")
String debug() {
    return "debug";
}
~~~

**Predict before running:**

1. Spring MVC now registers `GET /api/internal/debug`, while `ReviewedEndpointPolicies.ALL` still has only four routes.
2. `everyApplicationRouteHasExplicitReviewedPolicy` **FAILS** because the actual route set now contains `(GET, /api/internal/debug)`.
3. Requests from `eva` to the debug endpoint get `403` from `anyRequest().denyAll()`, so the newly added endpoint was not left public.

This is the desired safety behavior: adding an endpoint forces a policy review. If the endpoint must stay blocked internally, you can add a `DENY` rule type to the inventory and handle it with `match.denyAll()` plus a denial test; if it should be opened, define a dedicated authority and test both authorized and unauthorized callers. **Never add `permitAll` just to make a test green if the endpoint is not meant to be public.**

### Experiment B — Forgetting the report-export endpoint's policy

Temporarily remove the `GET /api/reports/export` entry from the `REVIEWED` list, leaving the controller and tests unchanged.

Expected: the inventory test fails because the route exists without classification. At the same time, `newlyAddedExportHasItsOwnPermission` fails: `eva`, previously allowed to export reports, now falls through to `denyAll()` and receives `403` instead of `200`. Thus **a forgotten permission declaration is caught from two different angles**.

Restore the entry, re-run tests, and verify everything passes. This shows how policies fail safely when omitted while tests force the team to resolve missing classifications.

### Experiment C — Adding an overly broad rule

On an experimental branch only, change `anyRequest().denyAll()` to `anyRequest().authenticated()`. Now any account holder can reach unclassified URLs. `unlistedPathsAndMethodsAreDenied` must fail: for instance, `GET /api/unknown` is no longer blocked by Security (typically returning `404` for no controller) instead of `403`; a new controller endpoint lacking a policy would be exposed to every logged-in user.

Restore `denyAll()` and re-run tests. This verifies the fallback **actually enforces protection**, rather than just sitting in a config file.

### Experiment D — Accidentally granting export permission

Add `"report:export"` to `bob`'s authorities while keeping the expected matrix unchanged. `newlyAddedExportHasItsOwnPermission` will fail because `bob` gets `200` instead of `403`. If that were an intentional business change, update the permission matrix and tests deliberately; otherwise, restore least privilege.

### Triage workflow when a test turns red

1. Read the diff between `registered` and `ReviewedEndpointPolicies.keys()`; identify the exact new route, HTTP method, and path pattern.
2. Verify whether the endpoint author defined who owns/may access the data, the minimum authority needed, and any tenant/record-level distinctions.
3. Add or update the policy accordingly while keeping `denyAll()` as the fallback. If a route must stay closed, record an explicit `DENY` entry in the inventory.
4. Write `MockMvc` cases for unauthenticated, unauthorized, authorized, wrong method, and (for state-changing requests) CSRF.
5. Re-run the full suite; declare completion only when both **route coverage and authorization behavior** pass.

## 7. Limits of Inventory Checks and How to Extend Properly

The implementation above intentionally inventories **controllers in package `com.example.routeaudit`**. In a real project, ensure the entire HTTP surface is covered:

- **Controllers in other packages:** widen the filter to cover all application packages, not just one demo package. Do not accidentally omit controllers added by other modules.
- **WebFlux or functional routing:** routes declared with `RouterFunction` do not necessarily appear in MVC's `RequestMappingHandlerMapping`. Inventory the right runtime's APIs and test via `WebTestClient`.
- **Actuator, framework, GraphQL, WebSocket, management ports, or starter-provided routes:** these may be managed by separate mapping infrastructures. Evaluate them explicitly instead of claiming MVC tests cover the whole system.
- **Multiple `SecurityFilterChain`s:** a chain with too narrow a `securityMatcher` can leave routes outside its scope. Tests must verify the right chain handles each route and that a fallback chain covers everything else.
- **HTTP `HEAD`/`OPTIONS`, CORS, and proxy preprocessing:** Spring MVC may support implicit methods beyond `@GetMapping`. This exercise's inventory lists only explicitly declared methods; when supporting HEAD, CORS preflights, or reverse proxies, test those paths separately.
- **Resource-level authorization:** `hasAuthority("document:read")` does not decide whether `alice` may read a document belonging to `bob` or another tenant. Enforce checks in the business layer and test cross-owner/cross-tenant data.
- **Dynamic policies:** a simple static list illustrates the concept. As groups and resources grow, you can extract a manifest, endpoint classifier, or custom `AuthorizationManager`, preserving the invariant that **live routes and reviewed policies are two independently comparable sources**.

Do not treat this test as a substitute for risk assessment and real data authorization tests. It specifically solves the problem of **adding an MVC endpoint without declaring or verifying its access policy**.

## 8. Common Mistakes

- **Writing tests only for old endpoints:** the test suite can stay green while a new endpoint goes completely unmentioned. Use dynamic mapping inventory tests.
- **Testing only `/api/unknown`:** `403` on a nonexistent URL proves the fallback works, not that a new route has a reviewed policy.
- **Auto-generating the policy inventory from all controllers:** both sides always match, so adding an endpoint never fails the test. The inventory must be updated only after human policy review.
- **Using `anyRequest().authenticated()`:** any logged-in user can invoke newly added unclassified URLs. Keep `denyAll()` until explicitly permitted.
- **Matching only paths and ignoring HTTP methods:** an approved GET does not mean POST/DELETE on the same path is approved.
- **Confusing `401`, `403`, `404`:** unauthenticated, forbidden, and missing handler are three distinct causes. Combine mapping inventory, status, and body checks to isolate causes.
- **POST missing CSRF creating a false "passing" test:** always add `csrf()` when testing write permissions, and add separate negative tests specifically for CSRF.
- **Inventoring part of the app and declaring the whole system secure:** cover every controller, filter chain, gateway, and routing mechanism in your architecture.

## 9. Completion Criteria and Official Documentation

This practical exercise is complete when the learner can:

1. Describe a concrete missed-endpoint scenario, distinguishing **accidentally left open** from **unreviewed**.
2. Explain the roles of `ReviewedEndpointPolicies.ALL`, method/path matchers, and `anyRequest().denyAll()`.
3. Run the `RequestMappingHandlerMapping` inventory test and explain why adding `@GetMapping("/api/internal/debug")` without adding a policy fails the test.
4. Verify via `MockMvc` all of anonymous, missing-permission, authorized, wrong HTTP method, legacy permissions, and fallback behavior, explaining expected statuses and bodies.
5. Run red–green experiments (adding a route, removing a policy, relaxing the fallback, over-granting authority), predicting outcomes **before** running and restoring a green suite.
6. State the scope limits around MVC inventorying, CSRF, multiple filter chains, functional routes, and record ownership.

Further reading in official documentation:

- [Spring Security: Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security: Security Filter Chain](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security: MockMvc Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security: MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Framework: RequestMappingHandlerMapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)

**Principle to retain:** every new endpoint must pass two independent checks — **runtime blocks it until a policy exists**, and **CI requires every live mapping to be classified and permission-tested before release**.
