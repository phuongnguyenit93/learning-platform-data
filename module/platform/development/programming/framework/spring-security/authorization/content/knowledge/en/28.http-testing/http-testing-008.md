# HTTP Testing: `csrf()` and Distinguishing CSRF from Authorization Rules

In Spring Security for **Servlet / Spring MVC** applications, a `POST` request can receive **HTTP 403 Forbidden** even when the user is logged in and has the right role. The cause may be a **missing or invalid CSRF token**, an **authorization rule denial**, or another mechanism. Therefore, a test that only checks status code `403` is not enough to prove authorization is working properly.

This lesson focuses on `csrf()` in **Spring Security Test + MockMvc**, how to combine it with simulated users, and how to design test cases that pinpoint which layer blocked the request.

## 1. Two Independent Security Questions

**CSRF (Cross-Site Request Forgery)** asks: *Does a state-changing request carry anti-forgery proof bound to the current session/context?* Browsers automatically send session cookies to a target site when tricked by another site into submitting a request; a CSRF token is a defense for the site to verify request intent. CSRF does not decide whether a user is allowed to transfer money or modify a resource.

**Authorization** asks: *Does the authenticated user have sufficient permission for this action/resource?* Decisions typically rely on `Authentication`, roles/authorities, HTTP method, path, or method- and data-layer checks. A `hasRole("ADMIN")` rule does not validate CSRF tokens by itself.

**Authentication** is the third question: *Who is the caller?* In MockMvc, `user("alice").roles("ADMIN")` creates a simulated user for the request. It does not generate a CSRF token; conversely, `.with(csrf())` does not log anyone in or grant roles.

| Aspect | CSRF protection | HTTP authorization |
| --- | --- | --- |
| Typical config | `http.csrf(...)` / enabled by default | `http.authorizeHttpRequests(...)` |
| Question answered | Does the request need a valid token and supply the right one? | Does the principal have the right permission for the request? |
| Influenced by | HTTP method, CSRF `RequestMatcher`, token repository, token presence/validity | HTTP method, URL, role/authority, rule order, `Authentication` |
| MockMvc tools | `.with(csrf())`, `.with(csrf().asHeader())`, `.with(csrf().useInvalidToken())` | `.with(user(...))`, `@WithMockUser`, status assertions |
| When denied | Typically `403` | Can be `403` when authenticated but lacking permission; unauthenticated requests may be `401`, login redirect, or other per config |

**Never infer the cause from `403` alone.** If you omit a CSRF token on a `POST`, the request can be rejected by `CsrfFilter` before role checks ever execute. A test saying "USER must receive 403 when calling an ADMIN endpoint" that forgets `.with(csrf())` can pass even if the permission rule is misconfigured.

## 2. What Does `csrf()` in MockMvc Actually Do?

Static import of the helper from `spring-security-test`:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Common usage:

```java
mvc.perform(post("/transfers").with(csrf()));
mvc.perform(post("/transfers").with(csrf().asHeader()));
mvc.perform(post("/transfers").with(csrf().useInvalidToken()));
```

- `.with(csrf())`: attaches a **valid CSRF token** to the mock request, via request parameter by default. It lets the request pass the CSRF check so you can verify the authorization layer or controller behavior.
- `.with(csrf().asHeader())`: places the valid token in an HTTP header; useful when clients send tokens in headers rather than form parameters.
- `.with(csrf().useInvalidToken())`: deliberately attaches an invalid token to verify the request is rejected.
- Omitting `.with(csrf())`: on a request where CSRF config requires a token, the request lacks a token; this is a separate test case to confirm CSRF is being enforced.

This is a **per-request test helper**, distinct from the `HttpSecurity#csrf(...)` configuration method. The helper does not globally enable/disable CSRF, does not authenticate users, and does not alter `authorizeHttpRequests`.

Under default Servlet configuration, Spring Security applies CSRF to HTTP methods **not considered safe**, typically `POST`, `PUT`, `PATCH`, and `DELETE`. Safe methods `GET`, `HEAD`, `OPTIONS`, and `TRACE` are not blocked by the default CSRF matcher; the application must uphold the rule that safe methods cause no meaningful state mutations. Custom matchers can change which requests require CSRF.

Tokens are commonly stored via `HttpSessionCsrfTokenRepository`; this can be swapped for `CookieCsrfTokenRepository` or another repository. Reading tokens from parameters/headers and storing them depends on actual configuration. The MockMvc helper simulates valid requests in tests; it **does not** replace full browser-flow testing of fetching tokens, sending cookies, and rotating tokens on login/logout.

## 3. Complete Example: CSRF and ADMIN Role in One Test Suite

Suppose the business policy is:

- `POST /transfers` and `GET /transfers` are restricted to role `ADMIN`.
- `POST /public-submit` allows unauthenticated access via `permitAll()`, yet **still requires a CSRF token** under default configuration.
- All other endpoints are `denyAll()`.

Example for **Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit Jupiter**. In a Gradle Spring Boot project whose dependency versions are managed by the Spring Boot BOM, declare these dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/test/java/demo/CsrfVsAuthorizationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = CsrfVsAuthorizationTest.TestApp.class)
@AutoConfigureMockMvc
class CsrfVsAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void adminWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithValidCsrfCanCreate() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }

    @Test
    void adminWithHeaderCsrfCanCreate() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN"))
                .with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }

    @Test
    void userWithValidCsrfIsStillForbidden() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("bob").roles("USER"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminGetWithoutCsrfIsOk() throws Exception {
        mvc.perform(get("/transfers")
                .with(user("alice").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("listed"));
    }

    @Test
    void userGetWithoutCsrfIsForbiddenByAuthorization() throws Exception {
        mvc.perform(get("/transfers")
                .with(user("bob").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPublicPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/public-submit"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPublicPostWithCsrfIsOk() throws Exception {
        mvc.perform(post("/public-submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("public-accepted"));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({SecurityConfig.class, TestController.class})
    static class TestApp {
    }

    @Configuration(proxyBeanMethods = false)
    static class SecurityConfig {
        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            http
                .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(HttpMethod.POST, "/public-submit")
                        .permitAll()
                    .requestMatchers("/transfers").hasRole("ADMIN")
                    .anyRequest().denyAll()
                )
                .csrf(Customizer.withDefaults());

            return http.build();
        }
    }

    @RestController
    static class TestController {
        @GetMapping("/transfers")
        String listTransfers() {
            return "listed";
        }

        @PostMapping("/transfers")
        String createTransfer() {
            return "created";
        }

        @PostMapping("/public-submit")
        String submit() {
            return "public-accepted";
        }
    }
}
```

Run in a Gradle project configured with Java 17 and JUnit Platform:

```bash
./gradlew test --tests demo.CsrfVsAuthorizationTest
```

On Windows you can use `.\gradlew.bat test --tests demo.CsrfVsAuthorizationTest`. Expect **all 9 tests to pass** with the asserted HTTP codes; this example creates no network connections, databases, or real money transfers. The config/controller classes sit right inside the test for standalone illustration; in real projects, replace them with the application's own `SecurityFilterChain` and controllers.

### Reading Results Layer by Layer

| Test case | User | CSRF | Expected outcome | What is proven in the example config |
| --- | --- | --- | --- | --- |
| `POST /transfers` | ADMIN | Missing | `403` | Right role is still blocked by CSRF |
| `POST /transfers` | ADMIN | Invalid | `403` | Forged token is not accepted |
| `POST /transfers` | ADMIN | Valid | `200` | Valid token **and** sufficient permission |
| `POST /transfers` via header | ADMIN | Valid | `200` | Header-based token submission path works |
| `POST /transfers` | USER | Valid | `403` | CSRF satisfied; role policy denies |
| `GET /transfers` | ADMIN | Not sent | `200` | GET does not need CSRF by default, right role |
| `GET /transfers` | USER | Not sent | `403` | No CSRF requirement, yet missing permission |
| `POST /public-submit` | Anonymous | Missing | `403` | `permitAll()` does **not** exempt CSRF |
| `POST /public-submit` | Anonymous | Valid | `200` | Public endpoint requires no login, still needs token |

The key is test pairs where **only one variable changes**. For instance, keeping `POST /transfers` and `ADMIN` constant and changing missing token → valid token shifts the result `403` → `200`. Keeping a valid token and changing `ADMIN` → `USER` shifts `200` → `403`. That is far stronger evidence than an isolated `isForbidden()` test.

## 4. Why `403` Is Not Enough to Conclude the Cause

Under the example configuration, the simplified flow of a `POST /transfers` request is:

```text
MockMvc POST /transfers
       |
       v
Spring Security filter chain
       |
       +--> CsrfFilter: does request need CSRF?
       |        |
       |        +--> Yes, but token missing/invalid --> 403 (stop)
       |        |
       |        +--> Yes, valid token ----------+
       |                                        |
       v                                        v
Authentication / SecurityContext      AuthorizationFilter
                                                |
                                   +------------+-------------+
                                   |                          |
                              ADMIN role                  USER role
                                   |                          |
                                  pass                       403
                                   |
                             MVC controller
                                   |
                                  200
```

The diagram only illustrates decisions relevant to this lesson, not the full filter ordering across every configuration. In particular, method-level controls like `@PreAuthorize` or post-controller business logic can still deny a request even after it passes the URL permission layer.

**How to write trustworthy authorization tests:** supply `.with(csrf())` for unsafe requests first, then vary only the variable under test (role, authority, user, URL, HTTP method). **How to write trustworthy CSRF tests:** keep an authorized user and URL fixed, then vary the token among missing, invalid, and valid. Even `permitAll()` endpoints should have a missing/valid token pair if CSRF still applies.

For anonymous requests to permission-gated endpoints, do not assume the outcome is always `403`: an entry point may return `401 Unauthorized` (e.g. HTTP Basic), `302` to a login page (form login), or `403` per configuration. Both mechanisms must be tested against the exact active security chain.

## 5. How to Use `@WithMockUser` or `user()`

In the example, `.with(user("alice").roles("ADMIN"))` applies to **a single request**, giving explicit control over the user in each check. The `spring-security-test` library also provides an annotation:

```java
@WithMockUser(roles = "ADMIN")
@Test
void adminMayPostWithValidCsrf() throws Exception {
    mvc.perform(post("/transfers").with(csrf()))
        .andExpect(status().isOk());
}
```

The snippet above is an **excerpt from a test context that already has `mvc` and the endpoint**, requiring `import org.springframework.security.test.context.support.WithMockUser`; it is not a standalone class. The annotation sets up a user for the whole test method, yet **does not automatically attach a CSRF token** to `POST`.

Regarding roles, `.roles("ADMIN")` and `@WithMockUser(roles = "ADMIN")` create authority `ROLE_ADMIN` under default conventions; `.hasRole("ADMIN")` also checks `ROLE_ADMIN`. If using `.authorities("ADMIN")`, that is literal authority `ADMIN`, distinct from `ROLE_ADMIN`. Do not misdiagnose a `403` caused by a wrong role prefix as a CSRF error.

## 6. Diagnosing Unexpected `403` Responses in MockMvc

1. **Identify the request:** HTTP method, actual URL, matching `SecurityFilterChain`, and whether filters are active in the test. `GET` and `POST` on the same URL can have different rules.
2. **Isolate CSRF first:** for `POST`/`PUT`/`PATCH`/`DELETE`, run one check with `.with(csrf())` and one missing the token. If the config uses a custom repository/handler, inspect how tests supply the matching token. Do not apply `csrf()` mechanically when the app deliberately has matcher exclusions.
3. **Keep a valid token and check permissions:** pass `user(...).roles(...)` or `@WithMockUser`, verify `hasRole`, `hasAuthority`, `requestMatchers` order, `denyAll` rules, and method security checks.
4. **Inspect the denial source:** enable `org.springframework.security=DEBUG` logging (or `TRACE` in test environments when needed), and check for `MissingCsrfTokenException`, `InvalidCsrfTokenException`, or access denied decisions. Never deduce solely from status.
5. **Verify tests run with real security filters:** `@SpringBootTest` with `@AutoConfigureMockMvc` normally auto-registers filters. If building MockMvc manually from context, apply `.apply(springSecurity())`. `MockMvcBuilders.standaloneSetup(...)` does not guarantee running the app's security chain. Avoid `@AutoConfigureMockMvc(addFilters = false)` when testing CSRF/authorization.
6. **Cross-check controller behavior:** a valid token and right role only let the request past those security steps; validation, exception handlers, `@PreAuthorize`, or business logic can still return other errors. Do not force every test to expect `200` if the real endpoint responds differently.

A quick reading guide:

```text
POST + ADMIN + no csrf()        -> 403
POST + ADMIN + with csrf()      -> 200
=> Isolated the effect of CSRF in this case.

POST + ADMIN + with csrf()      -> 200
POST + USER  + with csrf()      -> 403
=> Isolated the effect of the role rule in this case.
```

In real projects, the two implications above only hold when other conditions remain fixed and you know the controller response does not change for unrelated reasons.

## 7. Misconceptions and Boundaries to Keep in Mind

**`permitAll()` does not mean `csrf().disable()`.** Granting public access is an authorization decision; CSRF still inspects unsafe requests within its protection scope. The `POST /public-submit` test above illustrates this.

**Adding `.with(csrf())` is not a "fix for 403" in production.** It is how valid tokens are supplied to mock requests in tests. Real applications must issue tokens to clients and return them properly; never remove CSRF just to turn tests green.

**Do not disable CSRF globally to simplify tests.** Configurations like `http.csrf(csrf -> csrf.disable())` alter the very protection mechanism under test. If an endpoint genuinely needs CSRF exemption, design a specific matcher scope based on client type and credential source, then add dedicated tests verifying that exact scope.

**"REST/stateless/JWT" does not automatically eliminate CSRF concerns.** Risk depends on whether browsers automatically attach credentials (session cookies, token-carrying cookies, HTTP auth, etc.) when sending requests. APIs accepting only Bearer tokens actively placed by JavaScript/code in the `Authorization` header have a different threat model; evaluate how clients actually authenticate before exempting CSRF.

**`csrf().asHeader()` does not prove every frontend integrates properly.** Real headers, cookie names, `SameSite`, CORS, tokens after login/logout, session expiry, and browser credential submission require suitable integration tests. `MockMvc` runs in a simulated Servlet environment—useful for verifying server rules, not a full browser emulation.

**Never use a missing-token request's status to "prove" authorization.** A negative authorization check should supply a valid token first to rule out the CSRF branch, alongside a positive check on the same endpoint with an authorized principal.

## 8. Checklist for Every Data-Writing Endpoint

- [ ] Confirm HTTP method and active security chain.
- [ ] Have a test where **authorized user + valid CSRF** achieves the expected success outcome.
- [ ] Have a test where the same user **missing CSRF** is blocked when CSRF is required.
- [ ] Have a test where the same user with **invalid CSRF token** is blocked.
- [ ] Have a test where **unauthorized user + valid CSRF** is denied per policy.
- [ ] If the endpoint is `permitAll()`, explicitly confirm whether CSRF is still required or intentionally excluded.
- [ ] If using custom forms/headers/cookies, test how clients actually submit the token.
- [ ] Ensure MockMvc truly runs Spring Security filters; never accidentally disable filters in test config.

## Official Reference Documentation

- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Cross-Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
