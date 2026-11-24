# user(), anonymous(), and Configuring Roles and Authorities for Requests in HTTP Testing

> Context: **Spring Security authorization**, **Servlet HTTP** testing with **Spring MVC Test (MockMvc)** and **Spring Security Test**. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x. WebFlux APIs use WebTestClient and a different testing toolkit.

## 1. Lesson Objectives

When writing HTTP tests for endpoints protected by Spring Security, simply calling `mockMvc.perform(get("/api/report"))` is not enough to exercise every permission branch. You need to actively attach an **identity to each request** and verify that the policy returns the right outcome.

After this lesson, you will be able to:

1. Use `user("alice")` to create a mock authenticated user on **a single MockMvc request**, and `anonymous()` to simulate anonymous access.
2. Distinguish `roles("ADMIN")` from `authorities(new SimpleGrantedAuthority("..."))` and understand the `ROLE_` prefix.
3. Combine `@SpringBootTest`/`@AutoConfigureMockMvc` or `springSecurity()` so Spring Security actually runs inside MockMvc.
4. Write tests for `permitAll()`, `authenticated()`, `hasRole()`, and `hasAuthority()` with users holding different permissions; verify HTTP 200, 401, and 403 per the API configuration.
5. Avoid confusing missing CSRF token errors with missing role/authority errors when testing POST/PUT/PATCH/DELETE.
6. Distinguish **simulating authentication for authorization tests** from **testing login flows, JWT decoding, or loading real UserDetails**.

## 2. Two Core RequestPostProcessors

Spring Security Test provides static methods in `SecurityMockMvcRequestPostProcessors`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
~~~

Sample requests:

~~~java
// Alice is treated as authenticated, with authority ROLE_USER by default.
mockMvc.perform(get("/api/me").with(user("alice")));

// Bob has two roles -> ROLE_USER and ROLE_ADMIN.
mockMvc.perform(get("/api/admin")
    .with(user("bob").roles("USER", "ADMIN")));

// Request simulates anonymous, not a normal authenticated user.
mockMvc.perform(get("/api/public").with(anonymous()));
~~~

The snippets above are only **statements inside a test method**, not standalone Java classes. They do not require `alice`/`bob` accounts to exist in a database and do not perform password verification. You can use `user(userDetails)` when you need to explicitly supply a `UserDetails` instance built for the test.

**Key takeaway:** `user()` sets a mock `Authentication` on the request so that **the application's filters and authorization decisions** can evaluate it as a logged-in user. This is not proof that the real-world login flow works.

### 2.1 user("name") for a Request

With `.with(user("alice"))`, Spring Security Test creates a user named `alice`. By default it has a dummy test password and role `USER`, corresponding to GrantedAuthority `ROLE_USER`. This can be customized:

~~~java
mockMvc.perform(get("/api/admin")
    .with(user("alice")
        .password("unused-password")
        .roles("ADMIN")));
~~~

The value `password("unused-password")` here is merely an **attribute of the mock principal** and is not passed through `AuthenticationProvider` for password verification. Do not write password authentication tests using `user().password(...)`.

The `roles("ADMIN")` method automatically creates `ROLE_ADMIN`; do not pass `roles("ROLE_ADMIN")` because values to `roles(...)` that already carry the prefix are rejected by the default builder.

### 2.2 anonymous() for a Request

~~~java
mockMvc.perform(get("/api/public")
        .with(anonymous()))
    .andExpect(status().isOk());
~~~

`anonymous()` simulates the security context of an anonymous user. Technically, Spring Security may use an `AnonymousAuthenticationToken` with an authority such as `ROLE_ANONYMOUS`, but the `authenticated()` rule **does not treat anonymous as truly authenticated**. This is not a browser "logout" action; it configures the context for **the tested request**.

`anonymous()` is especially useful if the test class has `@WithMockUser` or MockMvc is configured with a `defaultRequest` carrying a mock user: you can still test the unauthenticated branch for a specific request.

### 2.3 RequestPostProcessor Belongs to the Request, Not a Real Login Session

Each `perform(...)` call is constructed independently. When comparing multiple identities, pass `.with(user(...))` on **each request under test**. Do not assume a previous call logged in all subsequent requests.

If you want to test a user persisted via cookie/session across multiple requests, or test real Basic/Bearer authentication, create and pass the corresponding state in the test. `user()` does not replace testing session persistence, JWT signature/claim conversion, or authentication providers.

## 3. Roles and Authorities: Similar Syntax, Different Meaning

Spring Security ultimately evaluates `GrantedAuthority` elements on `Authentication`. A "role" is a **naming convention for an authority** (starting with `ROLE_` by default).

| How the mock user is built | GrantedAuthority in request | Typical matcher | Result |
| --- | --- | --- | --- |
| `user("a")` | `ROLE_USER` | `hasRole("USER")` | Allowed |
| `user("a").roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Allowed |
| `user("a").roles("ADMIN")` | `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Allowed |
| `user("a").authorities(new SimpleGrantedAuthority("ADMIN"))` | `ADMIN` | `hasRole("ADMIN")` | Denied under default prefix |
| `user("a").authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Allowed |
| `user("a").authorities(new SimpleGrantedAuthority("reports:export"))` | `reports:export` | `hasAuthority("reports:export")` | Allowed |
| `user("a").roles("ADMIN")` | `ROLE_ADMIN` | `hasAuthority("reports:export")` | Denied without that authority |

Rules:

- `hasRole("ADMIN")` by default looks for authority `ROLE_ADMIN`; `roles("ADMIN")` on the test user creates an authority using the same convention.
- `hasAuthority("reports:export")` checks for an **exact string**; it does not prepend `ROLE_`.
- `hasAnyRole("ADMIN", "AUDITOR")` and `hasAnyAuthority("reports:read", "reports:export")` follow the corresponding mechanism.
- `roles(...)` suits high-level roles; `authorities(...)` is useful for fine-grained permissions/scopes or when supplying an exact authority name.
- `roles("ADMIN")` and `authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` can produce the same GrantedAuthority data, though their expression in tests differs.
- Choose either `roles(...)` or `authorities(...)` on the same builder according to your intent. Do not arbitrarily chain both assuming they **accumulate**; check the overload/builder in use if you need a combined authority set.

Example passing a specific authority to a request:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/exports")
    .with(user("alice").authorities(
        new SimpleGrantedAuthority("reports:export")
    )));
~~~

If the application has a custom role prefix via security configuration, role hierarchy, `GrantedAuthorityDefaults`, or a JWT converter, **tests must accurately reproduce the GrantedAuthorities after mapping**. In particular, an OAuth2/JWT scope may be mapped to `SCOPE_reports.read`; testing `hasAuthority("SCOPE_reports.read")` must supply that exact string. Using `roles("ADMIN")` to "stand in" for `SCOPE_reports.read` will not prove equivalent permission.

## 4. Setting Up MockMvc Properly So Security Executes

The Spring Security test dependency is required. With Gradle Groovy DSL in a Spring Boot 3.x application:

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

Spring Boot dependency management/BOM should manage aligned versions; do not mix a `spring-security-test` of a different major version with the application's `spring-security-core`.

Two common approaches:

**Approach A — HTTP integration testing with Spring Boot:**

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityHttpTests {
    @Autowired MockMvc mockMvc;
    // @Test ...
}
~~~

In standard Spring Boot Test, `@AutoConfigureMockMvc` auto-configures MockMvc and registers filters from the application context by default. Consequently, `.with(user(...))`, `.with(anonymous())`, and rules in `SecurityFilterChain` are processed when requests execute through MockMvc.

**Approach B — Manually building MockMvc from WebApplicationContext:**

~~~java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

`springSecurity()` adds Spring Security Test integration, filters, and the appropriate `SecurityContext` wiring to MockMvc. If using `MockMvcBuilders.standaloneSetup(controller)` and forgetting to attach filters/security config, tests may return `200` for endpoints that should be blocked: they are only testing the controller, **not testing real security**.

**Useful check:** always have at least one negative `anonymous()` test against an endpoint requiring authentication and one test with a user lacking the authority. If both still return `200`, inspect `FilterChainProxy`, `securityMatcher`, test slices, and rules.

## 5. Complete Spring Boot Example: API and HTTP Policy

Suppose the API has these routes:

| Endpoint | Policy |
| --- | --- |
| `GET /api/public` | `permitAll()` |
| `GET /api/profile` | `authenticated()` |
| `GET /api/reports` | `hasRole("REPORTER")` |
| `POST /api/reports` | `hasRole("REPORTER")` **and** valid CSRF |
| `GET /api/exports` | `hasAuthority("reports:export")` |
| All other routes | `denyAll()` |

To run the example, create a Spring Boot project with the dependencies from section 4, package `example.requestsecurity`, and the corresponding files under `src/main/java/example/requestsecurity/`.

### 5.1 RequestSecurityApplication.java

~~~java
package example.requestsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestSecurityApplication.class, args);
    }
}
~~~

### 5.2 SecurityConfig.java

~~~java
package example.requestsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasRole("REPORTER")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("REPORTER")
                .requestMatchers(HttpMethod.GET, "/api/exports")
                    .hasAuthority("reports:export")
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

Key points to understand:

- Rules are evaluated **in first-match order**; always place specific rules before `anyRequest().denyAll()`.
- Configuring `httpBasic()` + disabling form login creates clear REST HTTP behavior: anonymous requests to protected routes typically receive `401`, while authenticated mock users lacking permission typically receive `403`.
- `csrf(Customizer.withDefaults())` preserves POST protection. A POST missing a CSRF token can return `403` **before** reaching the controller or evaluating role rules.
- This is an **HTTP security** configuration. It does not simulate a database user store, JWT converter, role hierarchy, or object-level authorization in services.
- For public endpoints, `permitAll()` allows anonymous requests as well; for `authenticated()`, any authenticated mock identity passes even without a specific role.

### 5.3 DemoApiController.java

~~~java
package example.requestsecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoApiController {

    @GetMapping("/api/public")
    public String publicPage() {
        return "public-ok";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "profile-ok";
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "reports-ok";
    }

    @PostMapping("/api/reports")
    public String createReport() {
        return "created-ok";
    }

    @GetMapping("/api/exports")
    public String exports() {
        return "exports-ok";
    }
}
~~~

The controller does not read roles from the body or headers itself. URL rules apply before the controller runs. When resource ownership or tenant permissions need checking, add service/method security policies rather than inferring from `ROLE_REPORTER` that the user can view all reports.

## 6. Complete MockMvc Test Suite: Varying Identity Per Request

Create file `src/test/java/example/requestsecurity/RequestSecurityApplicationTests.java`:

~~~java
package example.requestsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
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
class RequestSecurityApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCanReadPublicEndpoint() throws Exception {
        mockMvc.perform(get("/api/public").with(anonymous()))
            .andExpect(status().isOk())
            .andExpect(content().string("public-ok"));
    }

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mockMvc.perform(get("/api/profile").with(anonymous()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void defaultUserIsAuthenticated() throws Exception {
        // user("alice") has ROLE_USER by default.
        mockMvc.perform(get("/api/profile").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile-ok"));
    }

    @Test
    void userWithDefaultRoleCannotReadReports() throws Exception {
        mockMvc.perform(get("/api/reports").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reporterRoleCanReadReports() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(user("alice").roles("REPORTER")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports-ok"));
    }

    @Test
    void bareReporterAuthorityIsNotRoleReporter() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORTER"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void prefixedAuthorityMatchesHasRole() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ROLE_REPORTER"))))
            .andExpect(status().isOk());
    }

    @Test
    void reporterRoleAloneCannotExport() throws Exception {
        mockMvc.perform(get("/api/exports")
                .with(user("alice").roles("REPORTER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void exactExportAuthorityAllowsExport() throws Exception {
        mockMvc.perform(get("/api/exports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("reports:export"))))
            .andExpect(status().isOk())
            .andExpect(content().string("exports-ok"));
    }

    @Test
    void reporterPostWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/api/reports")
                .with(user("alice").roles("REPORTER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reporterPostWithCsrfCanCreate() throws Exception {
        mockMvc.perform(post("/api/reports")
                .with(user("alice").roles("REPORTER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created-ok"));
    }

    @Test
    void anonymousPostWithCsrfStillRequiresLogin() throws Exception {
        mockMvc.perform(post("/api/reports")
                .with(anonymous())
                .with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "mai", roles = "REPORTER")
    void annotationAlsoSuppliesAuthenticatedRole() throws Exception {
        mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
    }
}
~~~

Run in the root of **the newly created demo Spring Boot project**:

~~~bash
./gradlew test
~~~

Or use `gradlew.bat test` on Windows. When the files are created in the right package, with dependencies and a compatible Gradle Java toolchain, the tests above are designed to pass. They rely on the specific `SecurityConfig` and endpoints in the lesson; you cannot run plain `javac RequestSecurityApplicationTests.java` because Spring Boot, Spring Test, and JUnit are required on the classpath.

### 6.1 Result Matrix

| Test identity | Request | Expected status | Interpretation |
| --- | --- | --- | --- |
| `anonymous()` | GET `/api/public` | `200` | `permitAll()` |
| `anonymous()` | GET `/api/profile` | `401` | Authentication required; demo uses HTTP Basic |
| `user("alice")` | GET `/api/profile` | `200` | Authenticated by default |
| `user("alice")` | GET `/api/reports` | `403` | Only has `ROLE_USER` |
| `user("alice").roles("REPORTER")` | GET `/api/reports` | `200` | Has `ROLE_REPORTER` |
| Authority `REPORTER` | GET `/api/reports` | `403` | Missing `ROLE_` prefix |
| Authority `ROLE_REPORTER` | GET `/api/reports` | `200` | Matches `hasRole("REPORTER")` |
| Only `ROLE_REPORTER` | GET `/api/exports` | `403` | Missing `reports:export` |
| Authority `reports:export` | GET `/api/exports` | `200` | Exact match for `hasAuthority(...)` |
| `ROLE_REPORTER`, missing CSRF | POST `/api/reports` | `403` | CSRF filter denies |
| `ROLE_REPORTER`, valid CSRF | POST `/api/reports` | `200` | Passes both CSRF and role |
| `anonymous()`, valid CSRF | POST `/api/reports` | `401` | CSRF does not replace login |

Expected HTTP statuses depend **specifically on the `SecurityFilterChain` in the example**. In applications with form login, custom entry points, JWT resource servers, or redirects, anonymous may see different results. Assert according to the actual API contract.

### 6.2 Why Both Positive and Negative Tests Are Needed

Tests that only confirm an authorized user can access a route do not catch a policy accidentally turning into `permitAll()`. For each rule, at minimum you need:

- Valid case: user holds the right role/authority → allowed.
- Insufficient-permission case: authenticated user with a different role/authority → denied.
- Anonymous case: unauthenticated → denied if the route requires authentication.
- For unsafe HTTP methods: a valid CSRF token to isolate the authorization decision.

Note that `authenticated()` does not mean `hasRole("USER")`: a valid principal holding `reports:export` without `ROLE_USER` can still satisfy `authenticated()`. Tests must match the actual rule.

## 7. Configuring Multiple Roles, Multiple Permissions, and Custom UserDetails

### 7.1 A User with Multiple Roles

~~~java
mockMvc.perform(get("/api/reports")
        .with(user("mai").roles("REPORTER", "ADMIN")))
    .andExpect(status().isOk());
~~~

The role list on the builder means `ROLE_REPORTER` and `ROLE_ADMIN`. If you need to assign an exact mix of `ROLE_REPORTER` **and** `reports:export`, use `authorities(...)`:

~~~java
mockMvc.perform(get("/api/exports")
    .with(user("mai").authorities(
        new SimpleGrantedAuthority("ROLE_REPORTER"),
        new SimpleGrantedAuthority("reports:export")
    )));
~~~

When testing role prefixes, remember `authorities(...)` does not automatically prepend `ROLE_`. This is where mock test data most easily diverges when real data comes from DB roles, JWT scopes, or a custom `GrantedAuthoritiesMapper`.

### 7.2 Attaching a Custom UserDetails

If the application needs a custom `UserDetails` with attributes beyond username, use the `user(userDetails)` overload. Structural example:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

UserDetails details = User.withUsername("test-user")
    .password("{noop}unused")
    .authorities("ROLE_REPORTER", "reports:export")
    .build();

mockMvc.perform(get("/api/exports").with(user(details)))
    .andExpect(status().isOk());
~~~

This is code **inside a test method**; the corresponding test file imports are required. The password set on the test object is not checked on this request. `user(details)` uses the object supplied by the test; it **does not verify that `UserDetailsService` loaded the right account**. To test loading accounts from the DB and real login, run a separate authentication flow test.

### 7.3 Distinguishing from @WithMockUser

The `@WithMockUser` annotation is handy if an entire method/class shares the same identity:

~~~java
@Test
@WithMockUser(username = "mai", roles = "REPORTER")
void reportIsAllowed() throws Exception {
    mockMvc.perform(get("/api/reports"))
        .andExpect(status().isOk());
}
~~~

It provides a `SecurityContext` for the corresponding test scope, whereas `.with(user("..."))` is clearer when **each request inside a test has a different identity**. For a test class applying `@WithMockUser` by default, use `.with(anonymous())` on a request where you want to explicitly simulate anonymous; or use `@WithAnonymousUser` if the whole method should be anonymous.

Do not use `@WithMockUser` to prove a password is correct, OIDC login succeeds, or JWT signature/claim mapping works. Real authentication-mechanism integration tests are needed for those goals.

## 8. Setting a Default Identity for MockMvc and Explicitly Overriding It

When many tests share the same role, a default request post-processor can be used:

~~~java
// Place in @BeforeEach or MockMvc setup method.
mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .defaultRequest(get("/").with(user("tester").roles("REPORTER")))
    .apply(springSecurity())
    .build();
~~~

Tests can call:

~~~java
// From defaultRequest: tester has ROLE_REPORTER.
mockMvc.perform(get("/api/reports"))
    .andExpect(status().isOk());

// This request explicitly replaces the identity with anonymous.
mockMvc.perform(get("/api/reports").with(anonymous()))
    .andExpect(status().isUnauthorized());
~~~

You need imports for `MockMvcBuilders`, `WebApplicationContext`, and `SecurityMockMvcConfigurers.springSecurity` in the setup class. When using `@AutoConfigureMockMvc` and `@Autowired MockMvc`, manual construction is usually unnecessary; the `defaultRequest` option is an alternative when a shared fixture is deliberately needed.

**Common pitfall:** configuring a default `ADMIN` user and forgetting to test negative paths. Whenever a test case unexpectedly passes with 200, check MockMvc's default identity, class-level `@WithMockUser`, and per-request `RequestPostProcessor`s.

## 9. Interaction with CSRF: Why POST Easily Leads to Wrong Conclusions

In standard Servlet Spring Security, CSRF protects unsafe methods (such as POST/PUT/PATCH/DELETE) when enabled. `user("reporter").roles("REPORTER")` **does not automatically attach a CSRF token**.

Three requests to the same route with different meanings:

~~~java
// Has REPORTER role but missing token: CSRF can block early (403).
mockMvc.perform(post("/api/reports")
        .with(user("reporter").roles("REPORTER")))
    .andExpect(status().isForbidden());

// Has REPORTER role and valid token: executed (200).
mockMvc.perform(post("/api/reports")
        .with(user("reporter").roles("REPORTER"))
        .with(csrf()))
    .andExpect(status().isOk());

// Lacks REPORTER role but has valid token: authorization denies (403).
mockMvc.perform(post("/api/reports")
        .with(user("reader").roles("USER"))
        .with(csrf()))
    .andExpect(status().isForbidden());
~~~

The first `403` test **does not prove the `hasRole` rule is working**: the error may be entirely due to `CsrfFilter`. When the goal is testing authorization on a POST, pass `.with(csrf())` to get past the CSRF layer first and then inspect the role/authority outcome.

You can use `csrf().asHeader()` or `csrf().useInvalidToken()` when testing CSRF protection specifically. Do not disable CSRF globally just to make POST tests run if the real application uses cookies/sessions and needs that protection. If the API truly uses self-submitted bearer tokens and disables CSRF under a verified threat model, tests must reflect **the exact production configuration**, not guess from the word "REST".

## 10. Does Testing with user() Prove Real Authentication?

**No.** These are two distinct problems:

| Testing goal | Suitable tool | What is verified |
| --- | --- | --- |
| Authorization for authenticated user | `.with(user("alice").roles(...))` | HTTP filters, role/authority rules, handlers |
| Authorization when anonymous | `.with(anonymous())` | Public/private endpoints, entry point |
| Testing real HTTP Basic | Request with HTTP Basic credentials, real or test-specific `UserDetailsService`/`AuthenticationProvider` | Authentication mechanism, password, account data |
| Testing JWT Bearer | Request with token, decoder/converter, and resource-server config | Signature/claims/expiry/authority mapping per test config |
| Testing session login | Login POST, cookie/session, and subsequent requests | Login filter, session handling |
| Testing user permission on objects | Mock identity + permission/tenant policy in service | Permission on specific resources, not just URLs |

Example HTTP Basic test (illustrative only; requires the test account configured in `UserDetailsService`):

~~~java
mockMvc.perform(get("/api/reports")
        .with(httpBasic("reporter", "actual-test-password")))
    .andExpect(status().isOk());
~~~

Requires static import `SecurityMockMvcRequestPostProcessors.httpBasic` and configuring `reporter`, password encoder, and matching roles. The complete example in section 5 does not provide a `UserDetailsService` for user `reporter`, so **do not treat this Basic snippet as a runnable test of the previous demo**.

Similarly with JWT, distinguish Spring Security Test's `jwt()` (mock token/authorities for authorization testing) from HTTP requests carrying a real Bearer JWT that gets decoded and validated. Both are useful, but they verify different steps.

## 11. Testing Role Hierarchies, Scopes, and Custom Authorization

Real systems are often more advanced than a standalone `hasRole("ADMIN")`:

- **Role hierarchy:** `ADMIN > MANAGER > USER` can allow `ADMIN` to satisfy `hasRole("USER")`. Correctness depends on the hierarchy being wired into the authorization engine; tests must load the actual hierarchy configuration rather than manually adding `ROLE_USER` to the principal and concluding the hierarchy works.
- **Custom role prefix:** Spring Security matches `ROLE_` by default; some config layers can change how roles are interpreted. Verify the exact authority string the authorization manager actually sees.
- **JWT scopes:** many resource servers map `scope`/`scp` to `SCOPE_x`. `user().authorities("SCOPE_x")` (with the proper overload) or `new SimpleGrantedAuthority("SCOPE_x")` tests **the matcher**, not the JWT converter.
- **Tenant/object-level permissions:** `hasAuthority("invoice:approve")` only ensures static permission. A user may hold this permission yet not be allowed to approve another tenant's invoice; you need domain-policy/method-security tests with resource data.
- **Multiple SecurityFilterChains:** if a test route matches a different chain than expected, you may see 401/403/200 outside the matrix. Check `securityMatcher`, chain ordering, and authorization rules.
- **Method security:** if a handler/service has `@PreAuthorize`, `@EnableMethodSecurity` must be enabled and tests must invoke via a Spring proxy. Calling an instance constructed with `new` directly will not prove the interceptor works.

How to reduce false positives: define a matrix of **route × method × principal × authorities × CSRF state** with both positive/negative cases, then assert the response and, when critical, assert the corresponding side effects/service invocations.

## 12. MockMvc Troubleshooting Checklist

| Symptom | Common possibility | How to confirm/fix |
| --- | --- | --- |
| Anonymous accessing protected route still returns 200 | Security filter chain not attached to MockMvc or route is `permitAll` | Check `@AutoConfigureMockMvc`/`springSecurity()`, `requestMatchers` |
| `user("admin").roles("ADMIN")` still gets 403 | Rule requires another authority, missing CSRF, different chain, or method security denies | Read exact rule and method, separate GET/POST tests |
| `authorities("ADMIN")` gets 403 on `hasRole("ADMIN")` | Authority missing `ROLE_` | Use `roles("ADMIN")` or authority `ROLE_ADMIN` |
| `roles("ROLE_ADMIN")` errors immediately on user creation | Builder already adds prefix automatically | Pass `roles("ADMIN")` |
| POST with right role still gets 403 | Missing/invalid CSRF token | Add `.with(csrf())` when testing authorization, or test CSRF separately |
| Anonymous request returns 302 | Form login entry point | Assert redirect per config instead of expecting 401 by default |
| Mock user gets 200 but real login is rejected | Tests bypass `AuthenticationProvider`/`UserDetailsService`/token decoder | Write real auth flow tests |
| User has scope in token but test matcher does not match | Converter produces `SCOPE_...` authority different from mock data | Check authority mapping and use the real string |
| One test uses the wrong identity | Class-level `@WithMockUser` or `defaultRequest` has another user | Override explicitly per request, test anonymous |
| `@PreAuthorize` test does not block | Method security not enabled or called outside Spring proxy | Use Spring context + `@EnableMethodSecurity`, call proxied bean |

**Do not write tests just to make CI green.** Role/authority fixtures must reflect the intended policy; avoid loosening production rules or disabling filters to match test results.

## 13. Self-Check Questions

1. `user("alex")` has `ROLE_USER` by default. Does it satisfy `authenticated()`? Yes. Does it satisfy `hasRole("ADMIN")`? No.
2. What authority does `roles("AUDITOR")` create? `ROLE_AUDITOR`, not `AUDITOR`.
3. For `hasAuthority("document:delete")`, does assigning only `ROLE_ADMIN` guarantee access? No; the exact authority or an additional policy is required.
4. Why is `anonymous()` still needed when a test suite has a default user? To verify the unauthenticated branch even when the default fixture supplies a user.
5. Why can a POST with `.with(user("reporter").roles("REPORTER"))` get 403 even with the right role? Missing CSRF token or another control layer.
6. Does `user("alice")` prove Alice exists in the database, has a valid password, and the JWT converter runs correctly? No. It explicitly supplies a mock principal to isolate authorization testing.
7. When changing a test from `roles("ADMIN")` to `authorities(new SimpleGrantedAuthority("ADMIN"))`, why does `hasRole("ADMIN")` turn from 200 into 403? Due to losing the default `ROLE_` prefix.
8. Is a single test where `GET /api/reports` with `ROLE_REPORTER` returns 200 enough to conclude the endpoint is safe? No: add negative cases (anonymous, missing role), unsafe methods/CSRF, and resource-level policies when needed.

## 14. Official Documentation

The URLs below target the Spring Security 6.5 branch, matching the APIs illustrated. If your project uses another major version, consult the corresponding reference:

- Running as a User in Spring MVC Test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- Setting Up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security test integration overview: https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html
