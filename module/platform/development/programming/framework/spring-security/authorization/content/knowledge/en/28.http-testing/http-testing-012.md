# Limitations of Mock Authentication vs Testing the Full Authentication Chain

> **Context:** Spring Security on the Servlet stack, HTTP testing with Spring MVC MockMvc. The focus is distinguishing testing **access permissions once an identity exists** from testing **how the system authenticates identity from an HTTP request**. Java examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x; the principles apply equally to corresponding newer versions.

## 1. Learning Objectives

After this lesson, you should be able to:

1. Accurately explain `Authentication`, `SecurityContext`, *authentication*, and *authorization*.
2. Point out what executes and what is bypassed when using `@WithMockUser`, `user(...)`, `authentication(...)`, or `jwt()`.
3. Choose suitable tests to catch password bugs, filter config bugs, JWT bugs, role/permission bugs, CSRF issues, and 401/403 responses.
4. Write at least one test sending real credentials through a simulated HTTP request instead of only pre-supplying an authenticated principal.

## 2. What Does "Mock Authentication" Actually Do?

In Spring Security, the `Authentication` interface describes a principal and security metadata: `principal`, `credentials`, `authorities`, and `isAuthenticated()` status. A `SecurityContext` typically holds the `Authentication` of the current request.

- **Authentication:** Verifies identity proof, such as username/password, HTTP Basic, or Bearer JWT. Only on success does it create/establish a trusted `Authentication` per configuration.
- **Authorization:** Once identity and permissions are known, decides whether the subject can access an endpoint or perform an action, such as `hasRole("ADMIN")` or `hasAuthority("SCOPE_reports.read")`.
- **Mock Authentication in tests:** The test pre-builds an `Authentication` or `SecurityContext` and injects it into processing. This **assumes the identity has already been authenticated** so you can focus on testing downstream behavior.

A realistic HTTP Basic flow usually looks like this (exact filters vary with configuration):

~~~text
HTTP request (Authorization: Basic ...)
    ↓
SecurityFilterChain
    ↓
Filter reading credentials
    ↓
AuthenticationManager / AuthenticationProvider
    ↓
UserDetailsService + PasswordEncoder (e.g. username/password)
    ↓
SecurityContext holding authenticated Authentication
    ↓
AuthorizationFilter / method security checks
    ↓
Controller / service
~~~

When using `@WithMockUser` or `with(user("alice"))`, the test **pre-populates** `Authentication` in the security context so downstream handlers see a user with the matching permissions. It does not prove HTTP headers are parsed properly, does not look up users from a data store, does not compare passwords, and does not run the real login chain.

**Important distinction:** Mocking a user **does not mean the whole filter chain is disabled**. When MockMvc integrates Spring Security properly, filters and authorization rules still run. What is skipped is **the path that constructs/verifies the real identity**; the exact degree of skipping depends on the mock technique and test configuration.

## 3. Mocking Techniques and What They Prove

| Technique | What the test pre-supplies | What it tests well | What it cannot prove |
| --- | --- | --- | --- |
| `@WithMockUser(username="alice", roles="READER")` | Mock user/authorities placed in the test's `SecurityContext` | Whether endpoint or method allows/denies `ROLE_READER`; how code reads principal | User alice exists, password is right, login request headers work |
| `mockMvc.perform(get(...).with(user("alice").roles("READER")))` | Mock user for that request | User/role authorization when running MockMvc | `UserDetailsService`, `PasswordEncoder`, HTTP Basic/form login |
| `with(authentication(customAuth))` | `Authentication` object built by the test | Logic relying on custom principal/authority types | Whether production actually constructs that object |
| `@WithUserDetails("alice")` | Loads `UserDetails` via service then builds context | User loading, authority mapping from the `UserDetailsService` used in test | Logging in with real password, HTTP credential parsing, `PasswordEncoder.matches(...)` |
| `with(jwt())` / `with(oauth2Login())` | Mock JWT/OAuth2 principal | Downstream handling given a JWT/OAuth2 principal and authorities | Signature check, token expiry, issuer, audience, real login/authorization server interaction |
| `with(httpBasic("alice","secret"))` | HTTP Basic header with username/password; no pre-built principal | HTTP Basic auth path, provider, user lookup, password check **if using real beans** | Real TLS/container/network; does not cover JWT or form login |
| `formLogin()` | Sends simulated form login request with valid CSRF via helper | Form-login filter, credentials, and login handling per config | Real browser, sessions/cookies across out-of-process infrastructure |

These helpers belong to `spring-security-test`. Outcomes depend on **how the test is wired**: if you mock `UserDetailsService`, `AuthenticationProvider`, or `JwtDecoder`, that component is still not genuinely tested, even if the request carries headers.

### A 200 Result Can Hide a Serious Bug

Suppose the database has no user `ghost`:

~~~java
@Test
@WithMockUser(username = "ghost", roles = "READER")
void readerCanOpenPage() throws Exception {
    mockMvc.perform(get("/me"))
        .andExpect(status().isOk());
}
~~~

The test can **PASS** because user `ghost` and role `ROLE_READER` were supplied upfront. It never queries the user store. Therefore, concluding "login succeeded with ghost" is **wrong**. The valid conclusion is: "if the request is processed under the context of an authenticated user holding `ROLE_READER`, the endpoint accepts it".

## 4. Comparative Test Example: Mock Principal vs Real HTTP Basic Credentials

The minimal example below uses Servlet MVC, Spring Boot Test, and a real `InMemoryUserDetailsManager` for the test environment. The same `GET /me` endpoint can accept a mock principal, yet when a request sends HTTP Basic, the password must match stored data.

Required dependencies in a Spring Boot 3.x project (versions managed by the Spring Boot BOM):

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

Create `src/test/java/example/AuthenticationBoundaryTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = AuthenticationBoundaryTest.App.class)
@AutoConfigureMockMvc
class AuthenticationBoundaryTest {

    @Autowired
    MockMvc mockMvc;

    // Only proves authorization after Authentication exists.
    // "ghost" is not in UserDetailsService.
    @Test
    @WithMockUser(username = "ghost", roles = "READER")
    void mockedReaderCanAccessWithoutExistingAccount() throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:ghost"));
    }

    // Credentials are converted into an HTTP Basic header and processed by the filter.
    @Test
    void basicAuthenticationChecksStoredPassword() throws Exception {
        mockMvc.perform(get("/me").with(httpBasic("reader", "s3cr3t")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:reader"));

        mockMvc.perform(get("/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/me").with(httpBasic("ghost", "whatever")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCredentialsYield401ButMissingAuthorityYields403()
            throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/me").with(user("reader").roles("VIEWER")))
            .andExpect(status().isForbidden());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableWebSecurity
    static class App {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            return http
                .authorizeHttpRequests(registry -> registry
                    .requestMatchers("/me").hasRole("READER")
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        }

        @Bean
        PasswordEncoder passwordEncoder() {
            return new BCryptPasswordEncoder();
        }

        @Bean
        UserDetailsService users(PasswordEncoder encoder) {
            return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                    .password(encoder.encode("s3cr3t"))
                    .roles("READER")
                    .build()
            );
        }

        @Bean
        GreetingController greetingController() {
            return new GreetingController();
        }
    }

    @RestController
    static class GreetingController {
        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello:" + authentication.getName();
        }
    }
}
~~~

Run from a Spring Boot-configured Gradle project:

~~~bash
./gradlew test --tests example.AuthenticationBoundaryTest
~~~

**Expected outcome:** All three JUnit methods pass; no business stdout is required. Assertions confirm in turn: mocked `ghost` → HTTP 200; `reader/s3cr3t` → 200; wrong password/non-existent user → 401; missing header → 401; valid principal lacking role → 403.

Why is this example valuable?

- `@WithMockUser` bypasses user and password verification; the first test can pass even though `ghost` does not exist.
- `httpBasic(...)` generates a request header; with the real filter chain, `InMemoryUserDetailsManager`, and `BCryptPasswordEncoder`, the second test exercises user lookup and password matching.
- `with(user(...))` tests denied permissions without creating a real user. Because the request is **authenticated yet lacks sufficient permission**, `403 Forbidden` is right in the example configuration.
- `401 Unauthorized` in the Basic test reflects the lack of valid authentication. In real applications, status also depends on `AuthenticationEntryPoint`, login redirects, exception handling, and active login mechanisms.

**Remaining boundary:** MockMvc processes Servlet MVC via mock requests/responses inside the JVM; it does not open HTTP sockets or prove reverse proxies, TLS, browser cookies, containers, or external identity systems work. When transmission and deployment must also be validated, add integration/e2e tests sending real HTTP to a server on a random port.

## 5. How Many Test Layers Does the Authentication Chain Need?

No single technique suffices to prove every aspect. Combine layers according to risk:

| Layer | Example | Goal | Limitations |
| --- | --- | --- | --- |
| Logic/authorization test | Calling service with `@WithMockUser`; MockMvc `with(user(...))` | Access control, `@PreAuthorize`, principal handling, roles/authorities | Skips credential authentication flow |
| MockMvc + Spring Security filter chain | `@SpringBootTest` + `@AutoConfigureMockMvc`; `httpBasic(...)`, `formLogin()`, or real `Authorization` header | Request mapping, filters, providers, statuses, exception handling | Runs only in JVM; still depends on any mocked beans |
| Integration with real user store/decoder | Same MockMvc or HTTP test with test DB repository, real `PasswordEncoder`, and `JwtDecoder` | Catch user mapping bugs, password hashing, JWT signature/claim validation | May still stub IdP or out-of-scope dependencies |
| E2E HTTP against running server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client sending real cookies/headers/tokens | Closer to production traffic: HTTP, chains, sessions, redirects, runtime config | Slower, needs dependency management; still does not test production IdP service itself |

A `@WebMvcTest` + `@WithMockUser` test is very useful for **web-layer authorization rules**, yet only tests beans/filters actually loaded into the slice. `@AutoConfigureMockMvc(addFilters = false)` deliberately omits registered filters in MockMvc: never use its results as proof that `SecurityFilterChain`/CSRF are working.

### JWT Resource Server Case

For APIs using Bearer JWT, these tests answer different questions:

1. `mockMvc.perform(get("/api/reports").with(jwt().authorities(...)))`: Given an existing JWT principal carrying certain authorities, does the endpoint accept it? The `jwt()` helper exercises authentication APIs at a mock level, yet **does not prove** production's `JwtDecoder` decoded or verified signatures.
2. Sending `Authorization: Bearer <signed-token>` to a chain with a real `JwtDecoder`: does the system extract the token, verify signature, `exp`/`nbf`, issuer/audience (when validators are configured), and map claims → authorities?
3. Sending malformed, expired, wrong-issuer/audience, bad-signature, or scope-deficient tokens: does it reject as expected, and never accidentally accept forged tokens?

Example (**illustrative snippet only; requires an existing `/api/reports` controller, JWT security config, and matching imports**):

~~~java
mockMvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

The snippet above assigns `SCOPE_reports.read` directly. It **does not test** the converter mapping `scope`/`scp` to authorities. To test real mapping, pass through the configured `JwtAuthenticationConverter` or write dedicated converter tests rather than forcing authorities manually and concluding the converter works.

Similarly, `with(oauth2Login())`/`with(oidcLogin())` are convenient for testing controllers post-login, yet do not execute full redirects, authorization code exchanges, token validation, or real IdP interactions. HTTP integration/E2E or component tests cover those steps.

## 6. Essential Negative Cases

Having only a happy path returning 200 is usually not enough to catch exposed security configs. A test suite should pick meaningful cases for the real mechanism:

| Scenario | What must be proven | Common expectation |
| --- | --- | --- |
| No credentials to auth-required API | Endpoint is not open anonymously | 401 with HTTP Basic/Bearer; may redirect if form login configured |
| Non-existent username or wrong password | Provider actually checks credentials | Must not return 200; usually 401 with HTTP Basic |
| Valid user lacking authority | Authorization runs after authentication | 403 in HTTP Basic example |
| Right role/authority | Rule permits the right subject | 200/2xx per business logic |
| Forged signature, expired, wrong issuer or audience token | Decoder + validators take effect | Reject; usually 401 with Bearer |
| Real token lacking scope | Do not confuse auth error with missing permission | Usually 403 |
| POST/PUT/DELETE with CSRF enabled | CSRF policy takes effect | Missing or invalid token gets 403; valid token proceeds per permission |
| Requests to different URLs, methods, or filter order | `SecurityFilterChain` matches the right endpoints and order | Blocks/allows accurately per config |

**CSRF:** In Servlet apps with CSRF enabled, `POST`/`PUT`/`PATCH`/`DELETE` requests can return 403 **even when `Authentication` and roles are right**. When testing authenticated business actions, use `with(csrf())` if a valid token is needed; to verify CSRF protection, write dedicated missing-token or `with(csrf().useInvalidToken())` tests. Do not read every 403 as a missing role.

**Testing failures at the right layer:** If a controller takes `@AuthenticationPrincipal CustomUser` while tests use `@WithMockUser` (default principal type Spring Security `User`), principal type mismatches in production may be masked or push tests in the wrong direction. Use `@WithSecurityContext`/`authentication(...)` with the right principal type for business tests, and test real principal creation for authentication.

## 7. Common Pitfalls and Fixes

**Pitfall 1 — Using `@WithMockUser` to confirm "login with right password".** The annotation does not send username/password to `UsernamePasswordAuthenticationFilter`/`BasicAuthenticationFilter` and never calls `PasswordEncoder.matches(...)`. To test passwords, send credentials via `httpBasic(...)` or `formLogin()`; use real `UserDetailsService`/providers and verify invalid cases too.

**Pitfall 2 — Assuming having MockMvc means SecurityFilterChain ran.** With `MockMvcBuilders.standaloneSetup(...)` or filter-omitting config, authentication/authorization may not be integrated. With `MockMvcBuilders.webAppContextSetup(context)`, apply `springSecurity()`; with Boot, configure `@AutoConfigureMockMvc` and verify the filter chain is genuinely present. Never use `addFilters = false` for security tests.

**Pitfall 3 — Confusing `roles("ADMIN")` with `authorities("ADMIN")`.** In Spring Security helpers, `roles("ADMIN")` produces authority `ROLE_ADMIN`; `hasRole("ADMIN")` also checks `ROLE_ADMIN` by default. `authorities("ADMIN")` produces the exact string `ADMIN`, which normally fails `hasRole("ADMIN")`. With OAuth2 scopes, authorities typically carry the `SCOPE_` prefix depending on converter config.

**Pitfall 4 — Using `@WithUserDetails` and concluding password/OTP/MFA was tested.** The annotation can load a real user from the service, yet exercises neither credential verification nor second factors. Separate multi-step authentication tests from post-login permission tests.

**Pitfall 5 — Mocking `JwtDecoder` and claiming JWT signatures are valid.** If the decoder returns a canned `Jwt`, the test only proves the path after the decoder; write separate tests with a real decoder/validator and tokens signed with test keys to catch cryptographic and claim validation bugs.

**Pitfall 6 — Using mock annotations in tests sending HTTP to a live server.** `@WithMockUser` populates the `SecurityContext` of the test execution thread, which is not automatically transmitted over sockets to server requests. In `RANDOM_PORT` tests, supply credentials/tokens/cookies via the HTTP client.

**Pitfall 7 — Asserting only 200.** If protection is turned off, many happy paths still return 200. Always include unauthenticated, wrong-credential, insufficient-permission, and app-relevant mechanisms like CSRF.

## 8. Workflow for Designing Tests for a Protected Endpoint

Before adding tests, answer in sequence:

1. **What is the identity entry path?** HTTP Basic, form login, session, opaque token, JWT, SSO/OIDC, or something else?
2. **Which step is under test?** Constructing/verifying `Authentication`, mapping principal → authorities, or post-authentication authorization decisions?
3. **Which beans are real?** Are `SecurityFilterChain`, provider, `UserDetailsService`, `PasswordEncoder`, `JwtDecoder`, converter, repository, or IdP mocked/stubbed?
4. **What are the pass/fail criteria?** Valid and invalid credential pairs; authenticated lacking permission; anonymous; 401/403/redirect statuses; body/side effects.
5. **Is there at least one test that "cannot pass if authentication is disabled"?** For instance, wrong password gets 401, forged-signature token is rejected, missing header is blocked. That is stronger evidence than a mock-user 200 test.
6. **Is it consistent with the Servlet stack?** This lesson covers `MockMvc` and Servlet. Spring WebFlux apps require `WebTestClient` and its dedicated reactive test utilities.

### Short Self-Check Quiz

- A `@WithMockUser(roles="ADMIN")` test accesses `/admin` and gets 200. Does that prove admin exists in the database? **No.** It only proves the rule permits a mock principal with `ROLE_ADMIN`.
- An `httpBasic("admin","wrong")` test returns 401 when using a real provider and encoder. Does it test the password verification step? **Yes**, within the scope of HTTP Basic config and the test's real beans.
- A `with(jwt().authorities(...))` test returns 200. Does it prove the JWT is properly signed and unexpired? **No.** Send a real token via Bearer and use a real decoder/validator if you want to verify those properties.

## 9. Takeaways When Reviewing Tests

**Mock Authentication is a tool to isolate authorization, not proof of the entire authentication pipeline.** A solid testing strategy keeps mock tests concise across many permission scenarios, then supplements them with credential/token tests passing through the filter chain with real security beans, negative cases, and end-to-end HTTP when deployment risk warrants it.

### Official Documentation for Reference

- Spring Security — Testing / Spring MVC: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Running as a User in Spring MVC Test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Setting Up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Testing HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Testing OAuth 2.0 (JWT, OAuth2 login): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Framework — MockMvc vs HTTP end-to-end: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html