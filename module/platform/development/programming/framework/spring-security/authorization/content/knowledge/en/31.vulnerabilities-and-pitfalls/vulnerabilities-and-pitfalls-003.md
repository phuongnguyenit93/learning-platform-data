# Endpoint Outside Every SecurityFilterChain: Path Coverage Gap in Spring Security

## 1. The Problem and Learning Outcomes

In a Spring MVC application using **Spring Security (Servlet)**, a developer might write `anyRequest().authenticated()` or `anyRequest().denyAll()` and assume every endpoint is protected. That belief is false if the statement belongs only to a `SecurityFilterChain` with a narrow scope: a request that **does not match any chain** will not pass through the chain's security filters, including the authorization filter.

For example, an application declares a chain for `/api/**`, yet also has an endpoint `GET /admin/export`. If there is no fallback chain and no other independent safeguard, `/admin/export` can be called directly even without logging in.

Objectives of this lesson:
1. Explain the `DelegatingFilterProxy → FilterChainProxy → SecurityFilterChain` mechanism and how the first chain matching a request is selected.
2. Distinguish **a request outside every chain**, **a request entering a chain and getting `permitAll`**, **a request entering a chain and getting `denyAll`**, and **a request excluded from filters by `web.ignoring()`**.
3. Reproduce the defect, fix it with a final chain covering all requests, and use unit-style coverage tests and `MockMvc` to verify both scope and HTTP behavior.
4. Build a prevention checklist when adding new endpoints, changing matchers, configuring multiple chains, and deploying the application.

**Scope:** Spring Security Servlet (Spring MVC, `HttpSecurity`, `SecurityFilterChain`). WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity` with a different mechanism; do not mix the two APIs. Examples run on Java 17+, Spring Boot 3.3.x/Spring Security 6.3.x; the core principles and DSL also apply to Spring Security 6.5.

## 2. How Does Spring Security Select a Chain?

### 2.1. Two Independent Steps: Select the Chain, Then Decide Access

~~~text
HTTP request
    │
    ▼
Container servlet filter chain
    │
    ▼
DelegatingFilterProxy ("springSecurityFilterChain")
    │
    ▼
FilterChainProxy
    │  evaluates SecurityFilterChains in order
    ├── chain @Order(1), matcher "/api/**" ? ── match ──→ API chain filters
    │
    ├── chain @Order(2), matcher "/admin/**" ? ─ match ──→ admin chain filters
    │
    └── default chain, matcher "any request" ? ─ match ──→ fallback filters
          │
          └── no chain matches → chain security filters do not execute
                                        │
                                        ▼
                                 remaining filters / MVC
~~~

`FilterChainProxy` evaluates `SecurityFilterChain`s in order and **selects the first matching chain**. It does not combine chains to execute filters from every chain. When no chain matches, the authorization rules inside the chains do not run. Controllers can still receive the request because the servlet container and Spring MVC are separate layers.

An `HttpSecurity` normally has a default matcher matching every request. When you call `http.securityMatcher("/api/**")`, you **change the scope of the entire chain** to `/api/**`. The `anyRequest()` rule inside applies only to the set of requests that passed that outer matcher.

### 2.2. Comparing Matcher Types and Decisions

| Configuration | Effect | For `GET /admin/export` when chain only accepts `/api/**` |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Selects requests **evaluated by the entire chain** | Chain does not match, skips this chain |
| `authorizeHttpRequests(a -> a.requestMatchers("/api/admin").hasRole("ADMIN"))` | Authorization **inside the selected chain** | Has no effect on `/admin/export` |
| `authorizeHttpRequests(a -> a.anyRequest().denyAll())` | Denies remaining requests **within that chain** | Does not turn an `/api/**` chain into a catch-all |
| Final chain **without calling `securityMatcher(...)`** | Keeps the default matcher for all requests | Gets the chance to handle requests unmatched by earlier chains |
| `web.ignoring().requestMatchers(...)` | Configures bypassing security filters for corresponding paths | This is an intentional filter bypass, distinct from a matcher gap |

**Security note:** `permitAll()` means an endpoint is allowed **by an authorization rule inside a chain**, while relevant security filters can still run (such as HTTP security headers). `web.ignoring()` and an unmatched chain leave the request without those filters. Do not use `permitAll()` as an excuse to skip chain coverage checks.

### 2.3. Which Chain Is Responsible?

Suppose we have:
- Chain A: `@Order(1)`, `securityMatcher("/api/**")`.
- Chain B: `@Order(2)`, `securityMatcher("/admin/**")`.
- Chain C: no `@Order`, no `securityMatcher` (catch-all).

`GET /api/profile` goes to A; `GET /admin/export` goes to B; `GET /public/ping` goes to C. If C is removed, `/public/ping` belongs to no chain. If only A exists and declares `anyRequest().denyAll()` inside A, `/admin/export` still sits outside every chain. If the catch-all is placed before A, all requests may be captured by the catch-all first, leaving A no chance to run. Ordering is as important as matcher scope.

## 3. How the Vulnerability Appears in Practice

### 3.1. Faulty Configuration: One Narrow Chain, No Fallback

The following snippet is solely for reproducing the defect in a learning environment; **do not deploy** as a real application security configuration.

~~~java
// Faulty SecurityConfiguration snippet: protects only /api/**.
@Bean
@Order(1)
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
// No SecurityFilterChain covers /admin/** or other URLs.
~~~

Interpretation table:

| Request | Does `/api/**` chain match? | Result if no other policy exists |
| --- | --- | --- |
| `GET /api/profile`, unauthenticated | Yes | Authentication required (HTTP Basic typically returns 401) |
| `GET /admin/export`, unauthenticated | No | Controller may execute and return 200 |
| `GET /public/ping` | No | Controller may execute |
| `GET /does-not-exist` | No | MVC may return 404, but 404 **does not prove** the request is protected |

When you declare your own `SecurityFilterChain`, do not assume Spring Boot will automatically create an extra fallback chain protecting all URLs. Coverage policy for remaining URLs is the responsibility of the actual security configuration.

### 3.2. Consequences and Limits of Conclusions

An uncovered endpoint can be called without Spring Security HTTP authentication/authorization; chain filters such as `AuthorizationFilter`, `SecurityContextHolderFilter`, `CsrfFilter`, or `HeaderWriterFilter` also do not run for that request. The concrete impact depends on the method, resource, filter setup, and business logic: it can lead to data exposure, uncontrolled administrative actions, or missing security headers.

**Do not equate this with “all application protections disappear”.** Filters outside `FilterChainProxy`, business-layer checks, gateway authentication, and method security (if enabled) may still intervene. `FilterChainProxy` also has an `HttpFirewall` layer processing requests before selecting filters. The accurate statement is: the request **receives no protection from the filters of a `SecurityFilterChain`**, because no chain was selected. The demo intentionally omits independent safeguards to observe the vulnerability clearly.

### 3.3. Common Causes

1. **Specifying `securityMatcher` too narrowly:** protecting `/api/**` while forgetting `/admin/**`, `/actuator/**`, or new endpoints under `/internal/**`.
2. **Missing catch-all:** adding one or more specialized chains and failing to register a final chain without a restricted matcher.
3. **Misunderstanding `anyRequest`:** believing `anyRequest().authenticated()/denyAll()` applies application-wide even though the chain has a `securityMatcher`.
4. **Overly broad `web.ignoring()`:** e.g., ignoring `/admin/**` or `/**`; this is an explicit filter bypass.
5. **Changes to URLs, servlet mappings, context paths, HTTP methods, or dispatcher types:** the actual matcher behaves differently than expected, especially with multiple servlets or internal request dispatches.
6. **Chain order:** a catch-all placed before a specialized chain shadows the specialized chain. This is a **wrong chain** bug rather than “no chain matched”; both require tests.
7. **Multiple ports/management context:** administrative endpoints may run on a different port or application context; protection must be verified where the endpoints are actually deployed.

## 4. Correct Configuration: Specialized Chain Plus Full-Coverage Fallback

Safe strategy in the example: the `/api/**` chain requires login; the final chain does not call `securityMatcher`, permits only `/public/ping`, requires the `ADMIN` role for `/admin/**`, and **denies by default** for other paths. Only expose URLs that genuinely need to be public.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    // No securityMatcher declared => handles all remaining requests.
    @Bean
    SecurityFilterChain catchAllChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

In the code above:
- `@Order(1)` makes the API chain get evaluated first.
- The `catchAllChain` bean has no `@Order`, runs after ordered chains, and has a default matcher matching all requests.
- `requestMatchers("/public/ping").permitAll()` is intentional public access **inside a security chain**.
- `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority; users with only `ROLE_USER` are denied.
- `anyRequest().denyAll()` in the fallback ensures unfamiliar URLs are blocked. If the product requires a “login by default” rule, it can be replaced with `authenticated()` after classifying routes, though verifying policy completeness remains necessary.

**Architecture note:** the simple example enables HTTP Basic on both chains so 401 results are easy to observe. Real applications may use bearer tokens, sessions, OAuth2 Resource Server, or login forms; the choice of authentication mechanism does not change chain coverage rules. With multiple servlets or a separate management context, verify matchers using the corresponding actual requests rather than guessing from URL strings of another servlet.

## 5. Runnable Example: Spring Boot + Spring Security + MockMvc

### 5.1. Test Project

Create a small Spring Boot Servlet project (Java 17+, Gradle 8.5+, Spring Boot 3.3.x). Place the following files at their exact paths, with Java examples split into independent files. This project is for testing purposes only; controller data consists of mock values.

File `settings.gradle`:

~~~groovy
rootProject.name = 'security-chain-gap'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    sourceCompatibility = JavaVersion.VERSION_17
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
~~~

Use a Gradle wrapper compatible with the declared Spring Boot plugin. The following commands assume the project has `gradlew` and `gradlew.bat`; if created via Spring Initializr, the wrapper is usually included. The code does not require a database or real authentication service.

### 5.2. Application and Endpoints

File `src/main/java/example/chaingap/ChainGapApplication.java`:

~~~java
package example.chaingap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainGapApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainGapApplication.class, args);
    }
}
~~~

File `src/main/java/example/chaingap/DemoController.java`:

~~~java
package example.chaingap;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class DemoController {

    @GetMapping("/api/profile")
    String profile() {
        return "api-profile";
    }

    @GetMapping("/admin/export")
    String exportData() {
        return "admin-data";
    }

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }
}
~~~

File `src/main/java/example/chaingap/SecurityConfiguration.java` — **fixed configuration**:

~~~java
package example.chaingap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain catchAllChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

### 5.3. Tests Blocking the Vulnerability at Two Levels: Chain Coverage and HTTP Behavior

File `src/test/java/example/chaingap/SecurityCoverageTest.java`:

~~~java
package example.chaingap;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityCoverageTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy filterChainProxy;

    private SecurityFilterChain selectedChain(String path) {
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        request.setServletPath(path);

        return filterChainProxy.getFilterChains().stream()
                .filter(chain -> chain.matches(request))
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "No SecurityFilterChain matches GET " + path));
    }

    @Test
    void everyDeclaredEndpointHasAnAuthorizationFilter() {
        for (String path : List.of(
                "/api/profile", "/admin/export", "/public/ping")) {
            SecurityFilterChain chain = selectedChain(path);
            assertTrue(
                    chain.getFilters().stream()
                            .anyMatch(AuthorizationFilter.class::isInstance),
                    () -> "Missing AuthorizationFilter for GET " + path);
        }
    }

    @Test
    void apiRejectsAnonymousRequest() throws Exception {
        mvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAllowsAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/profile").with(user("alice")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-profile"));
    }

    @Test
    void adminRejectsAnonymousRequest() throws Exception {
        mvc.perform(get("/admin/export"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRejectsAuthenticatedNonAdmin() throws Exception {
        mvc.perform(get("/admin/export")
                        .with(user("viewer").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminAllowsAdmin() throws Exception {
        mvc.perform(get("/admin/export")
                        .with(user("operator").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-data"));
    }

    @Test
    void publicPingStaysPublicInsideFallbackChain() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

**Why are two kinds of tests needed?**

- `selectedChain(...)` accesses the chain list and finds the **first chain matching** the simulated request; if no chain matches, the test fails at `orElseThrow`. It then checks `AuthorizationFilter` because **a chain may exist yet contain no authorization filter**. This assertion is tailored to the sample configuration using `authorizeHttpRequests`; systems using a different authorization filter need to adjust the assertion accordingly.
- `MockMvc` sends requests through the actually configured MVC and Spring Security pipeline. Status and body assertions test **effective access**, not just matcher strings. `with(user(...))` comes from `spring-security-test`; no real user accounts are needed for the fixture.
- The first test only covers the listed routes. A new endpoint does not automatically appear in that list; in production, maintain an endpoint/test inventory or a general check updated alongside API routing.

Run:

~~~bash
./gradlew test --tests 'example.chaingap.SecurityCoverageTest'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.chaingap.SecurityCoverageTest"
~~~

**Expected:** 7 tests pass on the fixed configuration; Gradle/JUnit may format summaries differently, so no hypothetical stdout string is assumed.

### 5.4. Reproducing the Vulnerability Yourself Before Fixing

Only in a local demo copy, **temporarily remove the entire `catchAllChain` bean**, keeping the `apiChain` bean intact; do not edit controllers or tests. Then rerun the test command:

- `everyDeclaredEndpointHasAnAuthorizationFilter` fails because `GET /admin/export` and `GET /public/ping` have no matching chain.
- `adminRejectsAnonymousRequest` fails: the demo returns 200 with `admin-data` despite expecting 401.
- `adminRejectsAuthenticatedNonAdmin` fails: the demo returns 200 instead of 403.
- `publicPingStaysPublicInsideFallbackChain` may still return 200, **but returning 200 does not prove the request went through a chain**. That is why the chain selection assertion is needed.

Restore the `catchAllChain` bean and rerun: the tests must return to passing. Reproducing by removing the bean clearly shows which configuration causes endpoints to fall outside protection.

You can observe this directly by running the application:

~~~bash
./gradlew bootRun
~~~

~~~bash
curl -i http://localhost:8080/api/profile
curl -i http://localhost:8080/admin/export
curl -i http://localhost:8080/public/ping
~~~

On the **correct** configuration: `/api/profile` and `/admin/export` return 401 for anonymous users, `/public/ping` returns 200 with body `pong`. With the **faulty `/api/**`-only** configuration, `/admin/export` in the demo returns 200 with body `admin-data`. This is the expected result from this specific fixture, not a universal conclusion for every application that has an extra gateway, method security, or other filters.

## 6. Diagnosing When an Endpoint Is Suspected of Sitting Outside Any Chain

### Step 1 — Identify the Actual Request

Record **HTTP method, URL, servlet path, context path, dispatcher type, and port**. The URL outside a reverse proxy may differ from the servlet path seen by the matcher. Check whether the endpoint is registered in Spring MVC or in the management application context. Do not rely on controller/method names to infer the URL with certainty.

### Step 2 — List Every Chain in Exact Order

Find all `@Bean SecurityFilterChain`s and `WebSecurityCustomizer`s, reading `@Order` along with `securityMatcher`. For each specific request: what is the first matching chain? Is there a final unrestricted chain? `anyRequest` only has meaning within the selected chain.

You can enable local logging via `src/main/resources/application.properties`:

~~~properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Typically, startup logs show which pattern each chain protects and which filters it contains; TRACE logs can show the matcher evaluation process and messages like **No security for ...** when no filters apply. Exact log formatting varies by version. Turn off trace after diagnosing to avoid writing sensitive information into production logs.

### Step 3 — Distinguish “No Chain Matched” from “Intentionally Bypassed”

| Observation | Possibility | How to Verify |
| --- | --- | --- |
| No chain `matches(request)` | True matcher gap | `getFilterChains()` + exact request; HTTP tests |
| A chain matches but `getFilters()` is empty | Likely bypass/ignoring | Inspect `WebSecurityCustomizer`, logs, and filter contents |
| Chain has `AuthorizationFilter`, `permitAll` rule | Public route permitted by authorization | Test headers/filter behavior and intended rule |
| Chain has `AuthorizationFilter`, deny rule | Endpoint must be blocked per rule | Test 401/403 with anonymous and each permission |
| Chain matches but wrong policy | Wrong authorization inside chain, not a chain gap | Check `requestMatchers` order, authorities, principal |

`FilterChainProxy#getFilters(String)` is only a convenience helper for inspection; when a matcher depends on servlet mapping, HTTP method, or request attributes, a URL string alone is not enough. Prefer testing with `MockMvc` and/or a simulated request reflecting the exact servlet path/method, as in the test above.

### Step 4 — Verify Behavior, Not Just Status

Test anonymous, regular user, and privileged user. Observe side effects: exporting data, writing to DB, calling external services. `403` or `401` does not automatically prove the right chain was selected: a gateway or another mechanism might also deny it; inspect the chain and configuration. Similarly, `404` does not prove a URL is safe: it may simply be a non-existent endpoint.

### Step 5 — Lock Down the Coverage Policy

Ensure every endpoint belongs to at least one appropriate chain, has the proper authorization policy applied, has regression tests, and has clear ownership. Do not silence alerts simply by putting `permitAll("/**")`. The fallback should be `denyAll` or `authenticated` per approved application requirements, with public exceptions explicitly declared.

## 7. Pitfalls to Avoid

1. **Placing `.anyRequest().authenticated()` only inside a narrow chain.** That is not a catch-all; there must be a second chain with an unrestricted matcher.
2. **Assuming that declaring `@EnableWebSecurity` guarantees every URL is protected.** The actual configuration of all `SecurityFilterChain`s determines coverage.
3. **Using `web.ignoring()` for dynamic or sensitive endpoints.** If a URL must be public, normally use `permitAll` inside a chain so security headers and necessary filters still apply.
4. **Ordering the fallback chain incorrectly.** `FilterChainProxy` only uses the first matching chain; the catch-all must come after specialized chains.
5. **Not testing dispatcher types and servlet mappings.** A passing GET test does not represent POST, ERROR, FORWARD, URLs with a different context path, or a different servlet.
6. **Relying solely on HTTP status 200/401/403.** Combine chain selection assertions, effective filters, and business permissions. Other independent protections can hide a chain gap.
7. **Testing only known endpoints and stopping.** New endpoints can be added later; update security coverage tests in the same change as routes.
8. **Claiming all filters vanish when no chain matches.** Only the security filters of `SecurityFilterChain` do not run; container filters, `HttpFirewall` in `FilterChainProxy`, and other mechanisms must be evaluated separately.
9. **Configuring separate security for the management port and then ignoring it.** If management runs on a different context/port, verify the exact set of chains and management endpoints there.

## 8. Checklist for Real Projects

- [ ] Listed all `SecurityFilterChain`/`WebSecurityCustomizer` beans and their evaluation order.
- [ ] A final chain covers requests unmatched by specialized chains, except for exclusions explicitly designed and verified separately.
- [ ] `requestMatchers` in each chain match the right authorities/policies; `anyRequest` is not mistaken for application-wide.
- [ ] Public routes use `permitAll` inside a chain when appropriate, instead of accidentally lacking a chain.
- [ ] Anonymous / regular user / privileged user tests exist for sensitive URLs.
- [ ] Tests verify routes belong to a chain and the chain contains the required authorization filter.
- [ ] Variations in HTTP method, servlet path, ERROR/FORWARD, and management port are tested when they exist.
- [ ] Side effects are checked in addition to status codes for state-changing endpoints.
- [ ] Security coverage tests are updated alongside adding or modifying endpoints.
- [ ] Verified in the actual deployment environment, where reverse proxy and base path may differ from dev machines.

## 9. Official References

- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): explains `securityMatcher`, chain ordering, default matcher, and consequences when no chain matches.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `anyRequest`, `permitAll`, `denyAll`, recommendation to use `permitAll` instead of ignoring.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, security filter chains.
- [Spring Security 6.5 — MockMvc Test Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): configuring Spring Security integration with Spring MVC tests.
