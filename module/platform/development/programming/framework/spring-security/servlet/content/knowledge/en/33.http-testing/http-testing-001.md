# Integrating MockMvc with springSecurity and the Real Filter Chain

> **Scope:** Spring Security 6.x on the Servlet stack (Spring MVC, Spring Boot 3.x, Java 17+, Jakarta Servlet), using Spring Security Test and MockMvc. The focus is on integrating `SecurityMockMvcConfigurers.springSecurity()` so that simulated requests **pass through the real Spring Security filters configured in the ApplicationContext**: `FilterChainProxy`/`SecurityFilterChain`, authentication, authorization, exception handling, and CSRF. "Real filters" here does not mean starting an HTTP server or running a real browser/Servlet Container; the request/response are still simulated by MockMvc.

## 1. The Problem to Solve

Suppose an application has an API that only allows users with the `REPORT_READ` authority to read reports, and only users with `REPORT_WRITE` to create reports. A plain controller test can invoke the handler directly and receive HTTP 200 even when the actual policy must reject it.

To reliably test **HTTP security**, we must send test requests through the same Spring Security mechanism the application uses, rather than only asserting what the controller returns.

There are three different questions:

1. **Does the controller behave correctly?** Given valid input, does the handler return the expected status/body?
2. **Does the HTTP security filter chain protect correctly?** Are unauthenticated requests rejected? Which authorities does the principal have? Does `CsrfFilter` block a POST missing a token? How does `ExceptionTranslationFilter` handle access denied/unauthenticated?
3. **Does real authentication work properly?** Are the authentication provider, `UserDetailsService`, password encoder, JWT decoder, IdP, and session/headers exercised along the corresponding path?

MockMvc + `springSecurity()` strongly supports questions (1) and (2); question (3) **is only verified for the real authentication components that the test request actually triggers**. For example, `httpBasic()` can cause the real `BasicAuthenticationFilter` and `AuthenticationProvider` to run on a mock HTTP request, whereas `@WithMockUser`/`user()` **pre-populates a fake authentication** and bypasses password verification.

**Upfront conclusion:** Use MockMvc **with the Spring Security filter chain** to test HTTP security. Do not merely "test that it returns 403", but also confirm **the exact reason for rejection**, which filter chain is running, and which kinds of authentication were or were not verified.

## 2. Relevant Components

| Component | Role |
| --- | --- |
| `MockMvc` | Simulates Spring MVC request/response without running a real TCP server. |
| `MockMvcBuilders.webAppContextSetup(context)` | Builds MockMvc from a `WebApplicationContext` with the controllers, filters, MVC config, and services in the context. |
| `MockMvcBuilders.standaloneSetup(controller)` | Builds a lightweight MVC setup around one or a few controllers; does not automatically bring in the full application configuration. |
| `SecurityMockMvcConfigurers.springSecurity()` | Attaches Spring Security Test integration to the MockMvc builder; uses the Spring Security `FilterChainProxy`/filter chain from the context in the appropriate setup. |
| `FilterChainProxy` | The delegate filter for Spring Security; selects the `SecurityFilterChain` matching the request and applies the security filters inside it. |
| `SecurityFilterChain` | The set of security filters for a configured request scope, typically defined via `HttpSecurity` and `@Bean`. |
| `DelegatingFilterProxy` | Bridges from the Servlet Container to the Spring-managed `springSecurityFilterChain` filter in a deployed application. |
| `SecurityContextHolder` | Where Spring Security components access the current `Authentication` according to the context strategy. |
| `SecurityMockMvcRequestPostProcessors` | Helpers such as `user()`, `httpBasic()`, `csrf()`, `jwt()`, etc. for test requests. |
| `@WithMockUser` | Creates a fake `Authentication` in Spring TestContext; convenient for testing authorization. |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Boot's way of building the app context and MockMvc, usually registering application filters with `addFilters=true` by default. |

A normal Servlet application has this conceptual flow:

~~~text
Real HTTP request
  -> Servlet Container
  -> DelegatingFilterProxy("springSecurityFilterChain")
  -> FilterChainProxy
  -> selects SecurityFilterChain matching request
  -> Security filters: context, CSRF, authentication, authorization...
  -> DispatcherServlet -> Controller
  -> HTTP response
~~~

Whereas a properly integrated MockMvc test looks like:

~~~text
MockHttpServletRequest
  -> MockMvc filter registration
  -> FilterChainProxy from Spring ApplicationContext
  -> selects matching SecurityFilterChain
  -> real Spring Security filters
  -> DispatcherServlet/Controller from WebApplicationContext
  -> MockHttpServletResponse
  -> status/headers/body/security state assertions
~~~

The difference is that **the container/network is simulated**, not that the entire **Spring Security chain is mocked**. That is the exact meaning of "real filter chain" in MockMvc.

## 3. Integrating springSecurity(): Two Common Approaches

### 3.1 Building MockMvc Manually from WebApplicationContext

When you use `MockMvcBuilders` directly, the common approach is:

~~~java
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup
        .MockMvcBuilders.webAppContextSetup;

MockMvc mvc = webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
~~~

The snippet above is **code inside a test class that has a `WebApplicationContext webApplicationContext` variable**, not a standalone Java SE application. When the context contains the `springSecurityFilterChain` bean from Spring Security, `springSecurity()` wires the helpers and filters required by Spring Security Test; requests will go through the configured Spring Security logic.

A complete test class example is in section 8.

**Distinction:** `springSecurity()` is a `MockMvcConfigurer` from Spring Security Test, **not** the `HttpSecurity` DSL. It does not create a new `hasRole` policy on its own. The policy still comes from the `SecurityFilterChain` bean in the app context.

### 3.2 Spring Boot @AutoConfigureMockMvc

In Spring Boot Test, the shorter way is:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HttpSecurityTest {

    @Autowired
    MockMvc mvc;
}
~~~

`@AutoConfigureMockMvc` creates `MockMvc` on top of the app context and **registers application filters by default** (`addFilters = true`), including the Spring Security filter if the application has configured it. In this common Boot setup, **you do not need to manually build MockMvc and call `.apply(springSecurity())` again**. Avoid accidentally attaching duplicate filter chains when letting Boot auto-configure it.

**Prerequisite check:** you must have the `spring-security-test` dependency, an appropriate security configuration, and filters registered in the context. A context where a test profile replaces `SecurityFilterChain` with another configuration will test **that test configuration**, not automatically the production configuration.

### 3.3 When Is Each Approach Better?

| Situation | Choice |
| --- | --- |
| Spring Boot app and you want to test multiple HTTP layers with real configuration | `@SpringBootTest` + `@AutoConfigureMockMvc`. |
| Manual control over MockMvc setup from `WebApplicationContext` | `webAppContextSetup(context).apply(springSecurity()).build()`. |
| Focusing only on controllers while mocking other dependencies | `@WebMvcTest`, but confirm which security config/filter chain is loaded. |
| Using only `standaloneSetup(controller)` | Insufficient to conclude full Spring Security integration, unless you **explicitly** attach the required filters/context. |
| Wanting to test real TLS, reverse proxy, servlet container, or network session behavior | Integration tests running a server/browser or staging environment; MockMvc does not replace them. |

**Do not use** `@AutoConfigureMockMvc(addFilters = false)` to test `SecurityFilterChain` behavior: that flag excludes application filters from MockMvc registration, which can make sensitive APIs return 200 without security filters running. It can be useful in clearly scoped **controller-only tests**, but test names and expectations must match that scope.

## 4. Spring Security FilterChainProxy and Chain Selection

Spring Security can have **multiple** `SecurityFilterChain` beans. `FilterChainProxy` iterates over the chains in configured order and typically selects the **first chain whose `RequestMatcher` matches**. Therefore, a MockMvc request must be tested with the exact method, path, and corresponding matcher conditions.

Conceptual rules example:

~~~text
@Order(1): /api/admin/**   -> admin security rules
@Order(2): /api/**         -> API security rules
@Order(3): /**             -> web security rules
~~~

If you place the general `/**` chain before `/api/admin/**`, a request may match the general chain first and **fail to be checked** by the intended admin policy. MockMvc going through the real `FilterChainProxy` helps catch this discrepancy when testing requests against the real paths.

Two levels of matchers must be distinguished:

- `http.securityMatcher(...)` / `SecurityFilterChain.matches(request)`: **selects which filter chain** is applied.
- `authorizeHttpRequests(...requestMatchers(...))` inside a chain: **decides authorization** for requests that have entered that chain.

A URL that matches no chain at all may proceed **without Spring Security protection**. Design chains to cover the exact areas needing protection and write tests for sensitive entry points, including different HTTP methods.

### Filters Do More Than Authentication

In a typical Spring Security chain, there may be filters handling `SecurityContext`, CSRF, logout, Basic/Form login, authentication exceptions, session management, and authorization. Exact filters, scope, and order depend on the DSL/version. Never hard-code assumptions that every app has the exact same filters or identical order.

For diagnostics, you can enable Spring Security logging at an appropriate level in a **test profile**:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Logs can show the request being processed by security filters and which chain was applied. Do not enable TRACE/DEBUG containing sensitive information in production just to inspect tests; avoid logging credentials, cookies, access tokens, and PII.

## 5. End-to-End Example Set: Real SecurityFilterChain Configuration

A Java 17+/Spring Boot 3.x example lets us cleanly distinguish authentication, authorization, and CSRF. Classes are placed under package `com.example.mocksecurity`, and tests in the corresponding package. This demo uses in-memory users; real applications use an appropriate user store/IdP and password management.

### 5.1 Maven Dependencies

Inside the `pom.xml` of a Spring Boot project (already using the Boot parent/BOM and Java 17+), add:

~~~xml
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
~~~

This is a **Maven configuration snippet**, not a complete POM. Spring Security Test must be on the test classpath and match the application's Spring Security version; rely on Spring Boot's dependency management rather than overriding versions arbitrarily.

### 5.2 Entry Point

File `src/main/java/com/example/mocksecurity/MockSecurityApplication.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(MockSecurityApplication.class, args);
    }
}
~~~

### 5.3 Security Configuration by HTTP Method and Authority

File `src/main/java/com/example/mocksecurity/SecurityConfig.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
                .requestMatchers(HttpMethod.GET, "/api/reports/*")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Key points to understand:

1. `GET /api/public` is allowed without authentication.
2. `GET /api/reports/{id}` requires the `REPORT_READ` authority.
3. `POST /api/reports` requires `REPORT_WRITE`.
4. `anyRequest().denyAll()` rejects any remaining undeclared endpoints/methods, preventing accidental open access.
5. `httpBasic` lets the demo send username/password via HTTP `Authorization: Basic ...` so it passes through the **real `BasicAuthenticationFilter`**.
6. `csrf.disable()` is not called. Spring Security enables CSRF protection by default for state-changing requests where applicable; therefore POST requests must carry a CSRF token in the corresponding tests.
7. `hasAuthority("REPORT_WRITE")` checks the exact authority name and **does not automatically prepend `ROLE_`**. With `hasRole("ADMIN")`, the default authority is `ROLE_ADMIN`.

This configuration is suitable for testing HTTP Basic behavior in the sample application, and is **not** automatically the right configuration for every REST API using stateless Bearer tokens. A bearer-only production API needs session/CSRF design tailored to its specific threat model, rather than reflexively disabling CSRF.

### 5.4 Users and PasswordEncoder for the Demo

File `src/main/java/com/example/mocksecurity/DemoUsersConfig.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-test-password"))
                .authorities("REPORT_READ")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("writer-test-password"))
                .authorities("REPORT_READ", "REPORT_WRITE")
                .build()
        );
    }
}
~~~

These two users are **for demo/test application use only**. Production source code must not contain real user passwords. `reader` can only read; `writer` can read and create reports. Because the app has a real `PasswordEncoder` and `UserDetailsService`, tests sending HTTP Basic with the correct password exercise the sample app's real authentication provider; a wrong password must be rejected.

Protecting username/password over HTTP Basic in deployment environments **strictly requires HTTPS**. MockMvc does not run TLS: tests cannot prove production transport protection is properly configured.

### 5.5 Controller to Clearly Observe Status and Body

File `src/main/java/com/example/mocksecurity/ReportController.java`:

~~~java
package com.example.mocksecurity;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping(value = "/api/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping(value = "/api/reports/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String readReport(@PathVariable long id) {
        return "report " + id;
    }

    @PostMapping(value = "/api/reports",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> createReport() {
        return ResponseEntity.status(HttpStatus.CREATED).body("created");
    }
}
~~~

The controller is intentionally minimal so that HTTP results clearly reflect security filter behavior. In a real application, beyond `REPORT_READ`, you must also verify **owner/tenant/resource ID** in the service/data layer; a general read authority alone does not prove a user is entitled to every report.

## 6. Test Suite Using @SpringBootTest + @AutoConfigureMockMvc

This is the most important part: using the **real `SecurityFilterChain`, users, and controller in the Spring ApplicationContext**, without disabling filters.

File `src/test/java/com/example/mocksecurity/ReportHttpSecurityTest.java`:

~~~java
package com.example.mocksecurity;

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

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/api/reports/7"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/reports/7")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void realBasicAuthenticationCanRead() throws Exception {
        mvc.perform(get("/api/reports/7")
                .with(httpBasic("reader", "reader-test-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("report 7"));
    }

    @Test
    void readerCannotPostEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "reader-test-password"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "writer-test-password")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerPostWithCsrfCanCreate() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "writer-test-password"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }

    @Test
    void invalidCsrfIsRejectedEvenForWriter() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "writer-test-password"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }
}
~~~

These tests use **`httpBasic(...)` to add an Authorization header**, rather than pre-constructing an already-authenticated `Authentication`. If the chain is genuinely registered, `BasicAuthenticationFilter` receives the header and passes through the sample app's `AuthenticationManager`/provider, `UserDetailsService`, and `PasswordEncoder`. Therefore, the wrong-password test carries much more meaning than a test using `@WithMockUser`.

Expected outcomes for **this specific illustrative configuration**:

| Test request | Notable rule/filter | Expected outcome |
| --- | --- | --- |
| Anonymous GET `/api/public` | `permitAll` | 200, body `public`. |
| Anonymous GET `/api/reports/7` | No auth and requires `REPORT_READ` | 401 (HTTP Basic entry point). |
| Reader sends wrong password via Basic | `BasicAuthenticationFilter`/provider verification fails | 401. |
| Reader sends correct password on GET report | Basic authentication succeeds, has `REPORT_READ` | 200, body `report 7`. |
| Reader POST with valid CSRF | CSRF passes, lacks `REPORT_WRITE` | 403 due to missing permission. |
| Writer POST missing CSRF | `CsrfFilter` rejects before reaching controller | 403 due to CSRF. |
| Writer POST with valid CSRF | Authenticated and sufficient authority | 201, body `created`. |
| Writer POST with invalid CSRF | Invalid CSRF token | 403. |

**Crucially:** both "reader lacks permission" and "writer missing CSRF" receive 403, yet they prove **two completely different things**. When testing authorization, always supply a valid CSRF token in POST tests so they do not pass for the wrong reason.

To run in a Maven project with the Spring Boot parent/BOM and all the classes above:

~~~bash
mvn test
~~~

Do not attach fabricated Maven stdout because test counts, plugin versions, and environments differ. With a consistent demo configuration, the assertions in this test class are expected to pass. If they fail, diagnose the cause via filter chain, credentials, request matchers, and CSRF; do not disable protections just to make tests "turn green".

### Why Is This HTTP Basic Test More Valuable Than Calling the Controller Directly?

If you call `new ReportController().readReport(7)` directly, the method returns `"report 7"` even if the caller has no permissions. That is not a bug in the demo controller, because authorization is placed at the Servlet filter chain. **Isolated controller testing cannot prove that the Servlet filter chain protects the request**.

Only an HTTP test passing through the real chain verifies that the `GET /api/reports/*` rule is enforced before the handler is invoked, that `BasicAuthenticationFilter` receives the header, and that the security components react as designed.

## 7. Manual Setup Using springSecurity() Instead of Boot Auto-Configuration

This is a **separate test class** illustrating how to build `MockMvc` manually from `WebApplicationContext`. Do not run this approach **simultaneously** with a MockMvc that is already auto-configured and adds a duplicate filter chain.

File `src/test/java/com/example/mocksecurity/ManualSecurityMockMvcTest.java`:

~~~java
package com.example.mocksecurity;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup
        .MockMvcBuilders.webAppContextSetup;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
class ManualSecurityMockMvcTest {

    @Autowired
    WebApplicationContext applicationContext;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = webAppContextSetup(applicationContext)
                .apply(springSecurity())
                .build();
    }

    @Test
    void securityChainAuthenticatesBasicCredentials() throws Exception {
        mvc.perform(get("/api/reports/9")
                .with(httpBasic("reader", "reader-test-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("report 9"));
    }

    @Test
    void securityChainRejectsUnknownUser() throws Exception {
        mvc.perform(get("/api/reports/9")
                .with(httpBasic("unknown", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Explanation:

1. `WebApplicationContext` holds the Spring MVC beans and the application's Spring Security filter chain.
2. `webAppContextSetup(...)` uses that context to build MockMvc.
3. `springSecurity()` wires the test integration and the appropriate Spring Security `FilterChainProxy` from the context.
4. The tests send HTTP Basic headers, so authentication code can execute on the mock request.
5. This uses the same demo app with `SecurityConfig` and `DemoUsersConfig` written above, not a second project with different users.

**Note:** If `springSecurity()` cannot find a filter chain in the ApplicationContext, that is a signal to check dependencies/security configuration—never replace it with a controller-only setup and claim the security tests ran.

### Is standaloneSetup Enough?

`standaloneSetup(controller)` is very useful for unit-style MVC tests, but it does not automatically build the full `FilterChainProxy`, security exception handling, service proxies, and Spring context configuration. To use it for security testing, you must explicitly supply the appropriate filters/beans and understand what remains missing. To test the "real filter chain" as required here, the safer and more maintainable way is **`webAppContextSetup(...).apply(springSecurity())` or `@AutoConfigureMockMvc` with filters enabled**.

## 8. Distinguishing Real HTTP Authentication from user() and @WithMockUser

Spring Security Test provides several ways to establish an identity in a test request. They do not have the same depth of verification.

### 8.1 .with(httpBasic("reader", "password"))

`httpBasic(...)` sets the `Authorization: Basic ...` header on the **MockHttpServletRequest**. When `BasicAuthenticationFilter` and authentication providers are present in the chain, the request **is authenticated through the app's real logic** such as `UserDetailsService` and `PasswordEncoder`.

It does not open a TCP connection, does not prove TLS, and does not call a real LDAP server if the app is configured with in-memory users. However, for the sample app, it tests the exact provider and password validation that are configured.

### 8.2 .with(user("reader")): Simulating an Authenticated Principal

Example:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;

mvc.perform(get("/api/reports/7")
        .with(user("not-in-database")
            .authorities(new SimpleGrantedAuthority("REPORT_READ"))))
   .andExpect(status().isOk());
~~~

This is a **test method snippet**, assuming a `mvc` variable, a mock request chain, and imports for `org.springframework.security.core.authority.SimpleGrantedAuthority` along with MockMvc static imports. `user(...)` sets a fake identity for **a single request**, without requiring `UserDetailsService` to look up the user and without checking a password.

Specifically, the non-existent username `not-in-database` can still access the endpoint, because the test **intentionally simulates** an already-authenticated user. Getting 200 only proves that the `REPORT_READ` rule accepts an `Authentication` carrying that authority.

### 8.3 @WithMockUser: Simulating SecurityContext at the Test Level

Test method example using the same `@SpringBootTest` MockMvc setup:

~~~java
@Test
@WithMockUser(username = "synthetic-user",
              authorities = "REPORT_READ")
void authorizationWorksForAnAlreadyAuthenticatedPrincipal()
        throws Exception {
    mvc.perform(get("/api/reports/7"))
        .andExpect(status().isOk());
}
~~~

`@WithMockUser` goes through a Spring TestContext listener to prepare the test `SecurityContext`. It does not invoke the HTTP Basic provider, does not load `synthetic-user` from a DB, and does not verify a password. With `@SpringBootTest`/`@AutoConfigureMockMvc` integrating Spring Security, the request is checked for **authorization** according to the test authorities.

Both `user()` and `@WithMockUser` are useful, **but must not be used as evidence that login or credential validation has been tested**.

### 8.4 Verification Scope Comparison Table

| Test technique | Effect | What it verifies | What it does not verify automatically |
| --- | --- | --- | --- |
| `with(user(...))` | Injects a fake Authentication/username/authorities for one MockMvc request. | URL authorization and handler behavior with a fake identity. | Password check, user store, login flow. |
| `@WithMockUser` | Sets a fake Authentication via Spring TestContext for the test. | Authorization against test user/authorities. | Credential/token validation, DB role mapping. |
| `with(httpBasic(...))` | Adds an Authorization Basic header. | `BasicAuthenticationFilter` and providers **if** they are in the installed chain. | TLS, container, other SSO/JWT pipelines. |
| `with(csrf())` | Adds a valid test CSRF token to the request. | CSRF protection interacting with the simulated request. | Protocol for obtaining/exchanging tokens from a real browser. |
| `with(jwt())` in Resource Server tests | Attaches a test JWT/authentication depending on helper. | Authorization rules based on constructed claims/authorities. | Real JWT signature/issuer/audience validation if the decoder is bypassed. |
| MockMvc with real request and filter chain | Runs Spring Security filters from the context on a mock request. | Triggered URL matchers, authn/authz/exception/CSRF behavior. | Real HTTP server, TLS, reverse proxy, browser cookie policy. |

**Do not use a vague label like "integration test".** Explicitly document which components a test exercised and which components were simulated.

## 9. CSRF: Avoiding a 403 That Passes for the Wrong Reason

When an application uses session/cookie-based authentication or a design exposed to CSRF risk, Spring Security typically uses `CsrfFilter` to protect state-changing requests. MockMvc tests must deliberately specify whether they are testing **CSRF** or **authorization**.

Important comparisons:

~~~java
// Authorization check: use a valid CSRF token so the request passes CsrfFilter.
mvc.perform(post("/api/reports")
        .with(httpBasic("reader", "reader-test-password"))
        .with(csrf()))
   .andExpect(status().isForbidden());

// Missing CSRF check: a writer with permission must still be blocked.
mvc.perform(post("/api/reports")
        .with(httpBasic("writer", "writer-test-password")))
   .andExpect(status().isForbidden());

// Happy path check: both permission and CSRF are valid.
mvc.perform(post("/api/reports")
        .with(httpBasic("writer", "writer-test-password"))
        .with(csrf()))
   .andExpect(status().isCreated());
~~~

These are **separate test snippets**, using the same demo app and `mvc` variable. If you omit `.with(csrf())` in the first test, you may receive 403 due to a missing CSRF token **even if you deleted the `hasAuthority("REPORT_WRITE")` rule**. At that point, the test "reader is rejected for lacking permission" **no longer proves** what its name claims.

Spring Security Test provides `csrf().useInvalidToken()` to test an invalid token. `csrf()` is a test post-processor that prepares the required token; it **does not imply** that a production browser received the cookie or hidden form field along the real path.

Beyond CSRF, there are CORS, SameSite, cookies, and sessions. MockMvc can verify header/filter behavior at the Spring layer, but it does not fully reproduce how browsers block cross-site requests/cookies. CSRF protection does not replace authorization; likewise, CORS is **not** a resource access control check.

## 10. Testing Anonymous Access, Access Denied, and Authentication Entry Points

HTTP status codes depend on the authentication configuration, not a fixed number across every application.

| Request state | With HTTP Basic demo config | With common form login |
| --- | --- | --- |
| Unauthenticated, accessing protected resource | 401 and usually `WWW-Authenticate`. | Usually 302 redirect to the login page. |
| Authenticated but lacking authority | 403. | 403. |
| POST missing/invalid CSRF token | Usually 403 due to CSRF. | Usually 403 due to CSRF. |
| Authorized and valid | 2xx depending on handler. | 2xx or redirect depending on controller. |

In the section 5 demo, `httpBasic(Customizer.withDefaults())` causes an unauthorized protected GET to typically return 401. If the real app uses `formLogin` instead of Basic, a test mechanically asserting 401 can fail because **302** is the correct behavior.

To make 401/403 tests meaningful:

1. Identify the `AuthenticationEntryPoint` and `AccessDeniedHandler` that the app uses.
2. Use the exact HTTP method/path; for POST, include a valid CSRF token when the goal is testing authorization.
3. Test the happy path with an authorized user to prove the endpoint is not blocked by a matcher typo or missing controller.
4. Inspect response status, location/headers where relevant, and ensure the body does not leak sensitive data.
5. Test missing credentials, wrong credentials, and valid credentials lacking permission **separately**.

If a test only asserts `status().isForbidden()`, you may not be able to distinguish "forbidden by role" from "missing CSRF" or another rejecting filter.

## 11. Notes on @WebMvcTest, @MockBean, and Sliced Configurations

`@WebMvcTest` is an **MVC slice test**, which can load controllers and MVC security-related configuration in test scope without loading the app's full set of services, repositories, or IdP beans. That suits many controller tests, but you must verify **which `SecurityFilterChain` configuration actually exists in the slice**.

Example risk:

- Production uses a custom chain with `hasAuthority("REPORT_WRITE")`.
- The slice test fails to import/configure that chain, or falls back to a different default chain.
- `MockMvc` has filters, but not the production rules you think you are testing.
- The test passes because mocked authentication and slice matchers differ from production.

To avoid false confidence:

- If the goal is the application's full HTTP filter chain, prefer `@SpringBootTest + @AutoConfigureMockMvc` or an appropriate context.
- If using `@WebMvcTest`, import the right security config, mock dependencies intentionally, and state that the test verifies a **slice**; inspect the loaded context/filters.
- Do not replace `SecurityFilterChain` with `permitAll` in tests just to get controllers to start. If you need a controller-only test, name and bound its scope clearly.
- Certain bean-mocking techniques or profiles can diverge from production behavior. Test documentation must specify which dependencies were mocked.

### Why Is addFilters=false Dangerous for Security Tests?

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

If you want to test the security filter chain, this annotation defeats the purpose because it disables the default registration of application filters on MockMvc. An unauthorized request can reach the controller directly. Only use it when you **intentionally test MVC/controllers without filters**, and never claim it proves HTTP security.

### standaloneSetup: Specific Limitations

`MockMvcBuilders.standaloneSetup(controller)` does not construct the full Spring `WebApplicationContext`; `@PreAuthorize` on a bean may not be proxied as in production if you pass a manually instantiated controller object. Filters, exception handlers, and configurers also do not appear unless you supply them. Therefore, "controller returns 200" in a standalone test does not prove the real app's HTTP path is secure.

## 12. Do HTTP Tests Verify Method Security?

**They can**, if method security is enabled, the service/controller is properly managed by Spring, and calls go through the interceptor/proxy. MockMvc sends the HTTP request through filters and then the MVC handler calls the service; if the service has `@PreAuthorize`, method security can run after the HTTP layer.

Example of an additional policy at the service layer:

~~~java
@PreAuthorize("hasAuthority('REPORT_READ') and " +
              "@reportAccess.canRead(authentication, #p0)")
public Report read(long reportId) {
    return repository.findById(reportId).orElseThrow();
}
~~~

This is an **architectural pattern**, not standalone Java code because `Report`, `reportAccess`, and `repository` are hypothetical domain components. For method security to work, `@EnableMethodSecurity` is required and calls must pass through a Spring-managed bean/interceptor. For production resource policies, `reportAccess` must verify owner/tenant from a server-side data store rather than trusting a client-supplied `ownerId`.

**Important:** if you used `@WithMockUser`, the method policy receives a fake principal. That helps verify the rule itself, but it does not test principal/role mapping from a real login. If the application uses a custom JWT/OIDC/SAML principal, test the appropriate principal type/claims or integration path.

In HTTP integration tests, you should test **at least two layers** for sensitive operations:

- URL authorization: only authorized roles can reach the route/method.
- Domain authorization: a user with the same role but a different owner/tenant is still blocked.

Do not rely solely on hiding UI buttons or checking `authenticated()`; neither prevents IDOR/BOLA.

## 13. Using JWT Resource Server / OIDC / SAML: Choose the Appropriate Request Post-Processor

HTTP Basic in the example is a convenient test because password verification is easy to observe. If production uses **Bearer JWT**, `with(httpBasic(...))` does not verify the right model. Pick the matching test approach:

### For a JWT Resource Server

- `with(jwt())` constructs a fake JWT/authentication for testing authorization by `scope`, claims, or authorities.
- Because the helper typically bypasses JWT decoder/signature validation, separately test **issuer, audience, expiry, and signature/key rotation** through a real decoder/filter or integration environment.
- To go through `BearerTokenAuthenticationFilter` and the real decoder, send a request with `Authorization: Bearer <test-token>` and configure appropriate test decoder/keys (do not call a production IdP).
- Ensure the JWT authorities converter is tested—for example, that scope becomes `SCOPE_reports.read`. Do not manually attach the authority in a mock and conclude the production converter always maps it properly.

### For OAuth2 Login / OIDC and SAML2 Login

Principal test helpers usually **do not** replay browser redirects, authorization code exchanges, or SAML Response signature verification. They only supply the authenticated state needed for controller/authorization tests.

To verify the real protocol flow, test against an IdP/AS sandbox, validly signed fixtures, or a controlled integration environment. Also test URL matchers, callback endpoints, session state, CSRF/SameSite where applicable, and post-mapping user permissions.

### For Sessions and Form Login

You can test with the `formLogin()` helper or send a POST login request to the actual login endpoint, then inspect status, session, and cookies as appropriate. Still, MockMvc does not fully replicate browser session cookie policies, domain/SameSite behavior, or TLS. When using a real browser/server to test UX and an external IdP, keep it as a **separate test suite** and do not conflate its conclusions with MockMvc tests.

## 14. Multiple SecurityFilterChains: How to Verify the Right Chain Is Selected

For an app with both an API and web pages, you can partition them:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

This is a **Java snippet inside a `@Configuration` class**, requiring imports for `@Bean`, `@Order`, `SecurityFilterChain`, `HttpSecurity`, and `Customizer`; it is not a standalone file. It illustrates chain selection via `securityMatcher`, **not configuration to paste directly into the section 5 demo app**. The two examples are **alternative setups**: pasting both `@Bean SecurityFilterChain` definitions into the same project without considering order/scope changes the outcome.

To verify correct chain selection:

1. Send anonymous `GET /api/...` and `GET /web/...` requests to observe the 401 vs. 302 difference if each chain's entry point is configured differently.
2. Send methods/paths that could overlap matchers (for example `/api/admin/**` before vs. after `/api/**`).
3. Check whether URLs outside all narrow matchers are protected by a fallback chain.
4. Do not treat an HTTP 200 from a controller when the filter chain was disabled as proof that the policy is correct.
5. Check logs/test config to confirm chain ordering and filter registrations; make specific assertions on the response.

**Note:** the second snippet has no narrow `securityMatcher`, making it a fallback chain; it should be ordered after specific chains rather than placed globally first where it would shadow the API chain.

## 15. Verifying SecurityContext, Principal, and Response

Spring Security Test provides matchers to verify authentication status after a request where appropriate, such as `authenticated()` or `unauthenticated()`. However, understand the request scope: with HTTP Basic, authentication processing may happen on every request; do not infer a persistent browser login session from this matcher alone.

Test snippet example:

~~~java
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;

mvc.perform(get("/api/reports/7")
        .with(httpBasic("reader", "reader-test-password")))
   .andExpect(status().isOk())
   .andExpect(authenticated().withUsername("reader"));
~~~

This is a **snippet inside a test class that has `mvc` and the required imports**, based on the demo configuration. It confirms Spring Security recognizes the request as authenticated with the corresponding username; you still must verify access control via HTTP status and returned data.

When working with async requests, sessions, or security context persistence, specific details may need dedicated tests: a single request does not prove authentication is stored or propagated correctly across another request or another thread.

### Do Not Leak Data in Tests

Do not call `andDo(print())` on responses containing tokens, passwords, personal data, or session IDs without filtering. Logging full Authorization headers or cookies can expose secrets in CI logs. For sensitive payloads, log only non-sensitive metadata or mask fields.

## 16. Minimum Test Scenarios for a Sensitive API

A meaningful HTTP security test suite should cover these categories of cases:

| Category | Example | Assertion needed |
| --- | --- | --- |
| Public | Anonymous GET `/api/public` | Public endpoint returns expected body/status. |
| Authentication | Anonymous GET protected | Blocked via the appropriate entry point. |
| Credentials | Sending wrong Basic password | Rejected by provider, never reaches protected handler. |
| Negative authorization | Reader POST with valid CSRF | Blocked for lacking `REPORT_WRITE`. |
| Positive authorization | Writer POST with valid CSRF | Executed, expected status/body returned. |
| Negative CSRF | Writer POST missing or invalid CSRF | Rejected by `CsrfFilter`. |
| Method/path coverage | GET, POST, PATCH, DELETE, new routes | No sensitive route is missed by matchers. |
| Resource-level | User with right role but wrong tenant/owner | Rejected or returns no out-of-scope data. |
| SecurityContext | Principal and authorities mapped properly | Do not rely on mock permissions to infer real login behavior. |
| Error handling | 401/302/403/404 per policy | No information leaks and no tests passing for the wrong reason. |

### Negative Tests Are Mandatory

Tests that only prove a writer can create a report will not catch an `anyRequest().permitAll()` mistake. You must test an unauthorized reader and an anonymous caller to verify the **rejection path**. Similarly, a test receiving 403 due to missing CSRF does not guarantee the endpoint has authorization. A good test suite deliberately sets conditions so that only **one cause** determines the outcome in each test.

### Protect Data, Not Just Endpoints

`hasAuthority("REPORT_READ")` on `GET /api/reports/*` does not automatically ensure each user sees only permitted reports. For resources identified by ID, there must be an owner/tenant/data-access policy. Testing that one user tries to read another user's report via direct URL is essential, even if the UI does not show that link.

## 17. When Tests Do Not Behave as Expected: Troubleshooting Table

| Symptom | Possible cause | Check / Action |
| --- | --- | --- |
| Anonymous GET protected returns 200 | Filter chain not attached to MockMvc, security matcher does not match, overly broad `permitAll`. | Check `@AutoConfigureMockMvc(addFilters=false)`, `springSecurity()`, chain order, and matchers. |
| Anonymous GET returns 302 instead of 401 | App uses form login or a redirect entry point. | Inspect the real chain config; adjust expectations rather than forcing Basic status codes. |
| `with(httpBasic(...))` still returns 401 despite right credentials | Wrong `UserDetailsService`/`PasswordEncoder`/provider or Basic filter not applied. | Check chain, username, hash, and test config. |
| `with(user(...))` passes while Basic password fails | `user()` bypasses credential validation by design. | Use Basic/form-login real request paths to test the authentication provider. |
| Reader POST returns 403 but removing the role rule still returns 403 | Test lacks a valid CSRF token so `CsrfFilter` blocks first. | Add `.with(csrf())` in authorization tests. |
| Writer POST still returns 403 despite correct role | Missing/invalid CSRF, missing exact permission, or wrong handler/matcher. | Distinguish `ROLE_*` vs authority, check CSRF and security debug logs. |
| `@WebMvcTest` behaves differently from production | Slice context does not load the same security config/providers. | Check which security beans are loaded; use `@SpringBootTest` when full context is needed. |
| Direct controller call passes even though live API forbids it | Does not pass through the filter chain. | Use MockMvc HTTP requests with filters enabled. |
| Adding manual `springSecurity()` to Boot auto-configured MockMvc causes duplicate filters | Chain/configurers registered twice. | Pick one MockMvc setup mechanism; do not attach duplicates. |
| An admin route goes through the general web chain | `/**` chain matches before the admin chain. | Set appropriate `@Order` and test each route. |
| `@PreAuthorize` does not execute even though filters run | Method security not enabled or direct/self-invocation bypasses the proxy. | Verify `@EnableMethodSecurity`, Spring-managed bean, and entry path. |
| Mock JWT test passes while production returns 401 | Mock JWT skips decoder/issuer/audience validation. | Test decoder/converter and real Bearer path separately. |
| MockMvc passes, production still fails on cookies/TLS | MockMvc does not run a real browser/proxy/network. | Add HTTP server/browser/staging tests with HTTPS and browser policies. |
| GET on the right endpoint leaks another tenant's data in body | URL-level authority is present but object-level authorization is missing. | Test and fix policy at the service/repository/data layer. |

## 18. Checklist Before Concluding a Filter-Chain Integration Test Is Trustworthy

1. `spring-security-test` is on the test classpath and compatible with the app's Spring Security version.
2. You know you are using **one of the two approaches**: Boot `@AutoConfigureMockMvc` (filters enabled by default) or `webAppContextSetup(...).apply(springSecurity())`.
3. MockMvc requests **actually pass through `FilterChainProxy` from the ApplicationContext**; `addFilters=false` or controller-only setup is not labeled a full security test.
4. The `SecurityFilterChain` beans in use are the intended configuration, not unexpectedly replaced by a test profile/slice.
5. Anonymous, wrong-credential, authorized/unauthorized, and happy-path cases are tested; both status and response content are asserted where meaningful.
6. For POST/PUT/PATCH/DELETE, the CSRF token is prepared specifically **for each test's goal**; a 403 from missing CSRF is not used to prove authorization.
7. `with(user())` / `@WithMockUser` (fake `Authentication`) is distinguished from `httpBasic()` or the real protocol authentication path.
8. If the app uses JWT/OIDC/SAML, there are separate tests for decoder/issuer/audience/signature and real authority/principal mapping.
9. Multiple chains, path/method matchers, `@Order`, fallback chains, public endpoints/callbacks, and bypass paths are checked.
10. Ownership/tenant/resource-level policies are tested; URL authentication does not replace data access checks.
11. Method security is enabled when testing method annotations and calls go through Spring-managed beans.
12. Do not conclude that MockMvc has tested TLS, reverse proxies, browser SameSite policies, or multi-node session behavior; supplement with real deployment tests.
13. Do not log credentials/tokens, session cookies, SAML assertions, or sensitive data into CI output.
14. Test results state clearly whether they verify the **Servlet security filter chain**, **authentication provider**, **authorization**, **CSRF**, or **business policy**, rather than just writing "security passed".

## 19. Summary

`springSecurity()` from Spring Security Test integrates the **Spring Security filter chain from the ApplicationContext** into a manually constructed MockMvc. In Spring Boot, `@SpringBootTest + @AutoConfigureMockMvc` with filters enabled achieves the same goal: routing mock HTTP requests through the real configured security filters and Spring MVC handlers.

Remember that **"real filter chain" does not mean "real HTTP server"**. MockMvc verifies framework logic on simulated requests/responses; using `with(httpBasic(...))` can verify the sample app's real Basic authentication provider, whereas `with(user(...))` and `@WithMockUser` intentionally skip credential verification. `csrf()` lets you separate CSRF from permission checks, preventing 403 tests from passing for the wrong reason.

**Practical rule:** *Ensure test requests actually pass through the target `SecurityFilterChain`, then isolate authentication, authorization, CSRF, object-level permissions, and the boundaries that MockMvc cannot simulate.*

## Official References

- Spring Security Reference — MockMvc Support: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security Reference — Security MockMvc Setup: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security Reference — MockMvc RequestPostProcessors: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html
- Spring Security Reference — Spring Security Architecture / FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/index.html
