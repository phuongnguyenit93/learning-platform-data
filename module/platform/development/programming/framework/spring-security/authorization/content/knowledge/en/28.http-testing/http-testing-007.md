# Testing Multiple Filter Chains and Undeclared Endpoints in Spring Security

## 1. Objectives and Scope

After this lesson, you can design and run HTTP tests for a **Spring Security Servlet/MVC** application with multiple `SecurityFilterChain`s, prove which chain is selected, test access when a URL is not listed in `requestMatchers` rules, and distinguish a path with no controller from a path unprotected by Spring Security.

The lesson uses **Java 17+, Spring Boot 4.1.2, Spring Security 7.x, JUnit Jupiter, and MockMvc**. This is a Servlet example; WebFlux applications use a different `SecurityWebFilterChain` mechanism.

## 2. Understanding the Decision Layers Precisely

Overall processing flow:

~~~text
HTTP request
  -> Servlet Filter / FilterChainProxy
     -> try SecurityFilterChain in @Order order
     -> select FIRST CHAIN with matching securityMatcher
        -> security filters: CSRF, authentication, authorization...
        -> authorizeHttpRequests: requestMatchers rules, then anyRequest
  -> Spring MVC DispatcherServlet
     -> find controller mapping, or return 404 if none
~~~

- `securityMatcher(...)` defines **the scope protected by the entire chain**. For example, `/api/**`.
- `requestMatchers(...)` inside `authorizeHttpRequests` defines **authorization rules once the request has entered that chain**. It does not decide which chain is selected.
- `@Order(1)` is evaluated before `@Order(2)`; the first matching chain handles the request. Chains do not stack filters or rules cumulatively. A chain without a `securityMatcher` has a default matcher matching all requests, making it suitable as a trailing fallback.
- `anyRequest().authenticated()`: URLs not matching prior rules in the chain can still be accessed by authenticated users. `anyRequest().denyAll()`: rejects all remaining URLs in the chain. Chain A's `anyRequest` does not apply to chain B.
- If **no chain matches**, Spring Security filters do not protect that request. An existing controller can serve it; a non-existent controller may return 404. This is a security risk if a fallback is accidentally omitted.
- Decisions by **security** and **MVC** happen in two separate stages. You cannot assume a URL with no controller always returns 404.

### Three Types of "Undeclared Endpoints"

| Scenario | Practical meaning | Outcome to test |
|---|---|---|
| A. Controller has `GET /api/profile`, not listed in `requestMatchers` | URL still belongs to `/api/**` chain | The API chain's `anyRequest` rule decides; in this example login is required |
| B. Controller has `GET /docs`, but URL does not match specialized chains | Enters the fallback (if present) | With `denyAll` fallback: denied, even though the controller exists |
| C. No controller for `GET /api/ghost` | URL still matches API chain before reaching MVC | Anonymous may receive 401; authenticated user passes authorization then receives 404 |

Having **neither a matching chain nor a fallback** differs from B: `/docs` can go straight to MVC without undergoing Spring Security authorization. Never conflate "unlisted in `requestMatchers`", "no matching chain", and "no `@GetMapping`".

### Reading HTTP Statuses Properly

- **200/201**: passed security and controller succeeded (201 for creation in the example).
- **401**: unauthenticated and HTTP Basic demands credentials; with form login this may be **302** to the login page.
- **403**: authenticated with insufficient permission, or request blocked by CSRF; inspect context to determine the cause.
- **404**: request reached MVC but no matching handler/controller existed. Security can completely reject the request before MVC returns 404.

## 3. Practice Scenario: Three Prioritized Chains

Suppose the application has:

1. **Admin chain**: `@Order(1)`, `securityMatcher("/api/admin/**")`, requires `ROLE_ADMIN`.
2. **API chain**: `@Order(2)`, `securityMatcher("/api/**")`; GET `/api/public` is public, other APIs require authentication.
3. **Fallback chain**: evaluated last, no `securityMatcher`; `/health` is public, all other URLs `denyAll`.

Because `/api/admin/reports` also matches `/api/**`, the admin chain must precede the API chain. If you swap the order, regular users can slip past the API chain's `authenticated()` rule and bypass the `ROLE_ADMIN` requirement.

Expected table (requests are GET, HTTP Basic enabled, controllers declared as in the example below):

| URL | Anonymous | ROLE_USER | ROLE_ADMIN | Reason |
|---|---:|---:|---:|---|
| `/api/public` | 200 | 200 | 200 | API chain, public |
| `/api/profile` | 401 | 200 | 200 | API chain, unlisted individually, falls into `authenticated` |
| `/api/admin/reports` | 401 | 403 | 200 | Admin chain has highest priority |
| `/health` | 200 | 200 | 200 | Fallback permits this exact URL |
| `/docs` (controller exists) | 401* | 403 | 403 | Fallback `denyAll` |
| `/api/ghost` (no controller) | 401 | 404 | 404 | API checks permissions first, MVC finds no handler |
| `/unknown` (no controller) | 401* | 403 | 403 | Fallback denies before 404 can occur |

Note *: when unauthenticated, `denyAll` combined with HTTP Basic's authentication initiation typically returns 401; the lesson's core tests use authenticated users so 403 outcomes are clear. Actual HTTP statuses also depend on entry point config, error dispatcher, and login mechanism.

## 4. Building a Runnable Example

Maven layout:

~~~text
security-routing-demo/
  pom.xml
  src/main/java/example/security/DemoApplication.java
  src/main/java/example/security/SecurityConfig.java
  src/main/java/example/security/DemoController.java
  src/test/java/example/security/SecurityRoutingTests.java
~~~

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-routing-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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

`spring-boot-starter-webmvc-test` provides MockMvc/JUnit test infrastructure; `spring-security-test` provides `user()`, `csrf()`, and identity simulation utilities. Maven uses dependency management from the Spring Boot parent, so there is no need to pin individual library versions manually.

### `src/main/java/example/security/DemoApplication.java`

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### `src/main/java/example/security/SecurityConfig.java`

~~~java
package example.security;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain generalApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Allow servlet to render errors after request processing.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/health").permitAll()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

No `csrf.disable()`: default CSRF protection is retained to test POST scenarios as well. `DispatcherType.ERROR` is permitted in the fallback so servlet error handling is not blocked a second time by `denyAll`; it does not turn a regular GET request into a public URL. If the project has multiple servlets, context paths, forwarding, or custom error endpoints, test the corresponding dispatchers.

### `src/main/java/example/security/DemoController.java`

~~~java
package example.security;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String apiPublic() {
        return "PUBLIC";
    }

    @GetMapping("/api/profile")
    public String apiProfile() {
        return "PROFILE";
    }

    @GetMapping("/api/admin/reports")
    public String adminReports() {
        return "REPORTS";
    }

    @GetMapping("/health")
    public String health() {
        return "HEALTHY";
    }

    @GetMapping("/docs")
    public String docs() {
        return "DOCUMENTATION";
    }

    @PostMapping("/api/items")
    @ResponseStatus(HttpStatus.CREATED)
    public String createItem() {
        return "CREATED";
    }
}
~~~

**Intentionally omit** any controller declaration for `/api/ghost` or `/unknown`; they are used to test "non-existent endpoints".

## 5. Testing All Paths with MockMvc

### `src/test/java/example/security/SecurityRoutingTests.java`

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRoutingTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointsWorkWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC"));

        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("HEALTHY"));
    }

    @Test
    void broaderApiChainRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/profile")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("PROFILE"));
    }

    @Test
    void specificAdminChainWinsBeforeBroaderApiChain() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/admin/reports")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/reports")
                .with(user("boss").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORTS"));
    }

    @Test
    void existingControllerNotAllowedByFallbackIsDenied() throws Exception {
        mvc.perform(get("/docs")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/docs")
                .with(user("boss").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingControllerInsideApiIs404OnlyAfterAuthorization() throws Exception {
        mvc.perform(get("/api/ghost"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/ghost")
                .with(user("alice").roles("USER")))
            .andExpect(status().isNotFound());
    }

    @Test
    void missingControllerOutsideApiIsBlockedByFallback() throws Exception {
        mvc.perform(get("/unknown")
                .with(user("boss").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsafeMethodRequiresCsrfToken() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/items")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("CREATED"));
    }
}
~~~

Run in the project directory with **JDK 17+ and Maven 3.6.3+**:

~~~bash
mvn test
mvn spring-boot:run
~~~

**All 7 test methods are expected to pass** when configuration and dependencies are correct. Statuses and response strings are `andExpect` assertions from source, not copies of actual Maven logs. If running the app with HTTP Basic outside tests, you must supply a real account configured by the app (such as Boot's temporary generated user if created); `user(...)` only creates a `SecurityContext` in tests, not production accounts.

### What Do the Tests Prove?

- `specificAdminChainWinsBeforeBroaderApiChain` tests **chain priority**. If `/api/**` were placed before `/api/admin/**`, a `ROLE_USER` user could slip into the admin endpoint because the API chain only requires `authenticated()`. The test catches this regression.
- `broaderApiChainRequiresAuthentication` proves `/api/profile` is still protected even though it has **no individual matcher** in `authorizeHttpRequests`.
- `existingControllerNotAllowedByFallbackIsDenied` proves having `@GetMapping("/docs")` does not imply access is allowed; the fallback still applies.
- `missingControllerInsideApiIs404OnlyAfterAuthorization` tests both before and after authorization: **401 for anonymous**, **404 for a valid user**. Asserting only 404 would miss a security hole.
- `missingControllerOutsideApiIsBlockedByFallback` proves `/unknown` is **denied before reaching MVC**.
- `unsafeMethodRequiresCsrfToken` isolates a 403 caused by CSRF. Holding `ROLE_USER` does not grant a CSRF token.

## 6. Testing the Risk of Missing a Fallback

**Analysis-only variant, do not add to the runnable app in section 4:** suppose the app declares only the `securityMatcher("/api/**")` chain and has no trailing catch-all chain. `GET /docs` will **bypass Spring Security's security filters**; if MVC has a `/docs` controller, requests can succeed without logging in. Therefore:

- Do not assume `.anyRequest().denyAll()` inside the **API chain** protects `/docs`; it only evaluates requests that already matched `/api/**`.
- Add a fallback `anyRequest().denyAll()` (allowlist policy) or `authenticated()` if you truly want all remaining URLs accessible only after login. Choose a policy deliberately, then write matching tests.
- Distinguish `permitAll()` (still passes through the filter chain with protections like security headers) from `web.ignoring()`/URLs completely outside chains (bypass many protections). Usually prefer `permitAll()` for public resources.

Do not test a truly non-existent URL to prove security exists: both a properly protected system and a system without a chain can return 404. Also test a **real controller** outside specialized chains (e.g., `/docs`) with both an unauthenticated user and an authenticated user.

## 7. Extending into a Strong Test Suite

A useful test matrix has independent axes:

| Axis | Minimum test cases |
|---|---|
| Chain priority | Specific pattern overlapping broad pattern; swapping order must break a test |
| Authorization | Anonymous, authenticated with wrong role, authenticated with right role |
| URL | Listed endpoint, unlisted endpoint with controller, URL without handler, URL outside specialized matchers |
| HTTP method | Permitted GET, POST/PUT/DELETE requiring right permission and CSRF |
| Boundaries | `/api/admin` vs `/api/admin/`; `/api/admin2`; query strings, case sensitivity, context/servlet path |
| Error dispatch | 404/403/401 when running in a real container, with `ERROR`/`FORWARD` conditions and `/error` page |
| Configuration | New chain bean, `@Order` changes, `securityMatcher` changes, fallback changes |

**Important:** `@WebMvcTest` only builds a partial application context; without importing full security config, tests may hit the default chain or a mock chain. To test **interactions across multiple real chains**, prefer `@SpringBootTest + @AutoConfigureMockMvc` and keep filters enabled (default). If building `MockMvcBuilders` manually, apply `springSecurity()` to attach `FilterChainProxy`. Never use `addFilters = false` for authorization testing.

With complex permissions or custom path matchers, also test HTTP methods, servlet paths, dispatcher types, reverse-proxy setups, and API paths without controllers. When full container behavior must be verified (forward/error dispatch, session cookies, redirects), add at least one real HTTP test with `@SpringBootTest(webEnvironment = RANDOM_PORT)`; MockMvc does not fully emulate the servlet container lifecycle.

## 8. Common Mistakes and Diagnosis

1. **Broad chain before narrow chain.** `/api/**` is evaluated before `/api/admin/**`, bypassing the admin role check. Keep `@Order` explicit and test overlapping matchers.
2. **Confusing `securityMatcher` with `requestMatchers`.** `requestMatchers` only picks rules *after* the chain has matched. One chain's `anyRequest` cannot cover URLs outside that chain.
3. **Missing or overly permissive fallback.** New controllers on URLs outside matchers may become exposed or accidentally public. Write tests for real URLs outside API chains.
4. **Asserting 404 for anonymous and ignoring 401/403.** Having no controller does not guarantee the request reached MVC. Always test the same URL under at least two login states.
5. **Reading every 403 as a wrong role.** For POST, missing CSRF tokens also return 403; use `with(csrf())` when testing authorization, and test CSRF separately if needed.
6. **Tests missing FilterChainProxy.** Manual MockMvc without security or setting `addFilters=false` makes every endpoint appear public. Re-check context and MockMvc config.
7. **Mixing up role/authority.** `hasRole("ADMIN")` checks `ROLE_ADMIN`; `user("boss").roles("ADMIN")` creates that exact authority. With `hasAuthority("ADMIN")`, supply the exact `ADMIN`.
8. **Different login mechanism yet hardcoding 401.** HTTP Basic can return 401, while form login usually redirects 302; assert per the chain's authentication entry point.
9. **Overly lenient matcher tests.** `/api/admin/**`, methods, servlet paths, and look-alike URLs must be checked against the actual matcher. Query parameters are not automatically path matcher criteria.
10. **Ignoring ERROR dispatch.** An MVC 404 can pass through `/error` in a real container and hit authorization again; separate security errors from routing errors.

To investigate, enable selective logging in the test environment:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access=DEBUG
~~~

Check which chain matched the request, what authorities `Authentication` carries, which authorization step decided the denial, and only then check controller mappings. Enable detailed logging only when needed; never log real credentials/tokens.

## 9. Self-Check Exercises

1. Change `generalApi`'s `@Order` to higher priority than `adminApi`. Which test should fail and why? **Answer:** `specificAdminChainWinsBeforeBroaderApiChain`; `ROLE_USER` could receive 200 instead of 403 on `/api/admin/reports`.
2. Change `generalApi.anyRequest().authenticated()` to `denyAll()`. Once logged in, does `/api/profile` still return 200? **No**, it gets 403 because it lacks a dedicated allow rule.
3. Remove the fallback while keeping controller `/docs`. Why is this a risk even if `/api/ghost` returns 404? **Because** `/docs` falls outside all chains and can still be served by MVC without Spring Security protection; 404 on a fake URL does not prove coverage.
4. For `GET /api/ghost`, why test both anonymous and a user? **Because** the respective 401/404 outcomes prove authorization ran before MVC discovered the missing handler.
5. For `POST /api/items` with `ROLE_USER`, why might 403 occur? **Because** default CSRF protects unsafe methods; add a CSRF token before testing the authorization rule.

## 10. Official Reference Documentation

- [Spring Security — FilterChainProxy and Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Multiple HttpSecurity Instances and securityMatcher Scope](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — authorizeHttpRequests, requestMatchers, anyRequest, denyAll](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing CSRF with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Testing Applications with MockMvc](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

**Principle to remember:** test **the first matching chain**, then test **that chain's authorization**, and only then consider **whether the controller exists**. A strong test suite must prove all three boundaries.