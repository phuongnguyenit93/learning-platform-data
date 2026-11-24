# spring-security-test, MockMvc, and Real Filter Chain Integration

In a **Spring Security Servlet + Spring MVC** application, an HTTP test can return `200 OK` because the controller is invoked directly via MockMvc without **ever running the security policy**. That is a testing bug that easily creates a false sense of security: JSON assertions still pass while `SecurityFilterChain`, authentication, authorization, or CSRF have not been tested.

The goal of this lesson is to configure `spring-security-test` with `MockMvc` so that requests pass through **the real `FilterChainProxy` from the `ApplicationContext`**, and then prove via tests that requests without credentials are blocked, invalid credentials are rejected, valid credentials lacking permission receive `403`, sufficient permissions reach the controller, and CSRF works for write methods.

**Example scope:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, JUnit Jupiter (JUnit 5), Spring MVC/Servlet, and HTTP Basic. The reactive `WebFlux`/`WebTestClient` model is not used in the runnable examples. On Spring Boot 4.x, some test auto-configuration packages change; read the Javadoc for the exact version instead of copying Boot 3.5 imports verbatim.

## 1. Three Testing Layers to Distinguish

| Testing style | Typical setup | Has the application's security chain? | When to use |
| --- | --- | --- | --- |
| Standalone controller | `MockMvcBuilders.standaloneSetup(controller)` | **Not automatically**; only filters added manually | Testing mapping, validation, serialization/controller logic in isolation |
| Web MVC slice | `@WebMvcTest(ReportController.class)` + `MockMvc` | May include Spring Security test infrastructure, but **not guaranteed to have the app's custom `SecurityFilterChain`**; must inspect/import required config | Fast testing of controllers and explicitly declared web policies |
| Full application context | `@SpringBootTest` + `@AutoConfigureMockMvc` | **Yes**, when filter registration is enabled (default `addFilters=true`) and app config is loaded | HTTP integration testing with security filters, user store, service/method security |
| Live HTTP end-to-end | `@SpringBootTest(webEnvironment=RANDOM_PORT)` + real HTTP client | Yes, via embedded server | When verifying network/port, container behavior, reverse proxy, or real cookies |

**`MockMvc` does not open an HTTP socket.** It uses Servlet API mock requests/responses to pass through Spring MVC and the registered filter chain. Therefore, "real filter chain" in the context of MockMvc means **the application's `SecurityFilterChain` beans executed by `FilterChainProxy`**, not a real browser, TLS, or real HTTP server. Those scenarios require tests running a real server.

Do not infer that a request passed through security just because:
- The `spring-security-test` dependency is in `pom.xml`.
- The test uses `@WithMockUser` or `with(user("..."))`.
- MockMvc returns `200` for the endpoint.
- The `@EnableMethodSecurity` annotation is present while instantiating the controller with `new`.

## 2. How the Components Work Together

~~~text
JUnit test
  |
  +-- @SpringBootTest: loads ApplicationContext and real beans
  +-- @AutoConfigureMockMvc: creates MockMvc, registers filters (by default)
  |
  v
MockMvc.perform(request)
  |
  v
Spring Servlet Filter chain
  |
  +-- DelegatingFilterProxy / springSecurityFilterChain
  |       |
  |       '-- FilterChainProxy
  |             |
  |             +-- SecurityFilterChain matching the request
  |             +-- Authentication filters: HTTP Basic, ...
  |             +-- CsrfFilter (for requests requiring CSRF)
  |             '-- AuthorizationFilter (URL rules)
  |
  v
DispatcherServlet -> Controller -> Spring-managed Service
                                  |
                                  '-- Method security (if enabled)
  |
  v
MockHttpServletResponse -> status, header, JSON, SecurityContext
~~~

`spring-security-test` provides:
- Request post-processors: `httpBasic(username, password)`, `user(...)`, `anonymous()`, `csrf()`, `jwt()`/`oauth2Login()` when the relevant module is present.
- Test annotations: `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails` along with mechanisms to populate `SecurityContext` before the test.
- Matchers/handlers supporting security checks, such as `authenticated()`, `unauthenticated()`.
- `SecurityMockMvcConfigurers.springSecurity()` for cases where you initialize `MockMvc` manually.

`spring-security-test` **does not automatically apply the application's real policy** to a controller built with `standaloneSetup`, nor does it prove real passwords via `@WithMockUser`.

## 3. Correct Dependency Setup

For a Maven Spring Boot **3.5.x** project inheriting the Spring Boot parent or importing the BOM, declare the following dependencies; starter and security-test versions are managed in sync by Boot:

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

This is a **`pom.xml` dependency snippet**, not a standalone `pom.xml`; the project must have the Spring Boot parent/BOM, build plugins, and appropriate Java 17 configuration. If using Gradle, the equivalent declarations are `implementation("org.springframework.boot:spring-boot-starter-web")`, `implementation("org.springframework.boot:spring-boot-starter-security")`, `testImplementation("org.springframework.boot:spring-boot-starter-test")`, `testImplementation("org.springframework.security:spring-security-test")`.

Check actual dependencies in Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

On Windows: `mvnw.cmd dependency:tree -Dincludes=org.springframework.security`. Do not mix `spring-security-test` version 7.x with a Spring Security 6.x runtime just to use newer test APIs. When an import does not exist, check the classpath/test scope and actual release.

## 4. Demo Application with a Real Filter Chain

To have testable code, we declare **a single** Spring Boot application in package `com.example.securitytest`. The files below form the complete application code; they can be placed into a Spring Boot 3.5.x project with the dependencies above.

**`src/main/java/com/example/securitytest/SecurityTestApplication.java`**

~~~java
package com.example.securitytest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTestApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` allows adding rules to services with `@PreAuthorize`. For ordinary URL checks, `SecurityFilterChain` remains the control layer before the controller.

**`src/main/java/com/example/securitytest/SecurityConfiguration.java`**

~~~java
package com.example.securitytest;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        // CSRF remains enabled by default.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader123")
                .authorities("REPORT_READ")
                .build(),
            User.withUsername("editor")
                .password("{noop}editor123")
                .authorities(
                    "REPORT_READ", "REPORT_WRITE", "REPORT_EXPORT")
                .build(),
            User.withUsername("guest")
                .password("{noop}guest123")
                .authorities("OTHER")
                .build()
        );
    }
}
~~~

Rule meanings:
- `GET /api/ping` allows anonymous access.
- `GET /api/reports/**` requires the `REPORT_READ` authority.
- `POST /api/reports` requires `REPORT_WRITE` and must still pass `CsrfFilter`.
- The final rule forces all other endpoints to be authenticated. In the example, `DispatcherType.ERROR` is permitted so underlying errors like 404 are not turned into authorization errors during error dispatch.
- `{noop}` is for demo only: storing plain-text passwords is not safe for production. Real projects need an appropriate `PasswordEncoder`, a real user store, or the corresponding authentication mechanism.

**`src/main/java/com/example/securitytest/ReportService.java`**

~~~java
package com.example.securitytest;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReportService {

    public Report get(long id) {
        if (id != 42L) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Report not found");
        }
        return new Report(42L, "Monthly");
    }

    @PreAuthorize("hasAuthority('REPORT_EXPORT')")
    public String export() {
        return "EXPORT-OK";
    }

    public Report create(String title) {
        // Hardcoded demo: does not write to database.
        return new Report(43L, title);
    }

    public record Report(long id, String title) {}
}
~~~

**`src/main/java/com/example/securitytest/ReportController.java`**

~~~java
package com.example.securitytest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/reports/{id}")
    public ReportService.Report get(@PathVariable long id) {
        return service.get(id);
    }

    @GetMapping("/reports/export")
    public String export() {
        return service.export();
    }

    @PostMapping("/reports")
    public ResponseEntity<ReportService.Report> create(
            @RequestBody CreateReport request) {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(service.create(request.title()));
    }

    public record CreateReport(String title) {}
}
~~~

`GET /api/reports/export` passes both the URL check `REPORT_READ` and `@PreAuthorize("hasAuthority('REPORT_EXPORT')")` on the service. This is a good scenario to verify that **the filter chain and method security run together**. `POST /api/reports` requires a CSRF token as well because the example intentionally **does not** disable CSRF.

## 5. Integration Testing: @SpringBootTest + @AutoConfigureMockMvc

This is the primary configuration for the goal of **testing the real security filter chain**:

~~~java
@SpringBootTest
@AutoConfigureMockMvc // addFilters = true by default
class ReportSecurityIntegrationTests {
    @Autowired MockMvc mvc;
}
~~~

`@SpringBootTest` creates the ApplicationContext with `SecurityConfiguration`, `ReportController`, `ReportService`, `UserDetailsService`, and `springSecurityFilterChain`. `@AutoConfigureMockMvc` configures MockMvc against that context and registers filters found in the context; there is no need to construct the controller with `new`. **Do not** add `@AutoConfigureMockMvc(addFilters=false)` to a test aimed at verifying security.

The following file covers the key behaviors.

**`src/test/java/com/example/securitytest/ReportSecurityIntegrationTests.java`**

~~~java
package com.example.securitytest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadProtectedReport() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Basic")));
    }

    @Test
    void wrongPasswordIsRejectedByAuthentication() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGuestLacksReadAuthority() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("guest", "guest123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerCanGetExistingReport() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Monthly"));
    }

    @Test
    void authorizedReaderGets404ForMissingRecord() throws Exception {
        mvc.perform(get("/api/reports/99")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void unauthenticatedRequestDoesNotReach404Decision() throws Exception {
        mvc.perform(get("/api/reports/99"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void editorWithoutCsrfTokenGets403() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor123"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithInvalidCsrfTokenGets403() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor123"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerCannotWriteEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "reader123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanWriteWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor123"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"New\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(43))
            .andExpect(jsonPath("$.title").value("New"));
    }

    @Test
    void readerPassesUrlRuleButFailsMethodRule() throws Exception {
        mvc.perform(get("/api/reports/export")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorPassesBothUrlAndMethodRules() throws Exception {
        mvc.perform(get("/api/reports/export")
                .with(httpBasic("editor", "editor123")))
            .andExpect(status().isOk())
            .andExpect(content().string("EXPORT-OK"));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void mockUserCanTestAuthorizationWithoutRealPassword() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isOk());
    }
}
~~~

Run all tests in a Maven project:

~~~bash
./mvnw test
~~~

On Windows run `mvnw.cmd test`; if there is no Maven wrapper, use `mvn test`. With a project and dependencies configured as in the example, **14 tests are expected to pass**. This is an outcome deduced from the sample code; it is not an execution log verified against a concrete project. Expected statuses include `200` (public/reader/export), `201` (create), `401` (no/wrong Basic credentials), `403` (missing permission/CSRF/method authority), and `404` (non-existent ID after passing security).

### Why Do These Tests Provide Strong Evidence?

1. **Wrong password returns 401:** `httpBasic("reader", "wrong")` only creates an `Authorization: Basic ...` header. It does not mark the user as authenticated. The `401` result only appears when the authentication filter/provider is invoked against the real user store.
2. **Authenticated guest lacking permission returns 403:** verifies `AuthorizationFilter` applies the `hasAuthority("REPORT_READ")` rule.
3. **POST with missing/invalid CSRF returns 403; with CSRF and permission returns 201:** verifies the real `CsrfFilter` runs, followed by authorization and the controller.
4. **URL passes but method denies:** verifies the service is Spring-managed/proxied and `@EnableMethodSecurity` takes effect.
5. **Authorized reader with missing ID returns 404:** proves the request passed through the filter chain to reach resource lookup logic; missing credentials with the same ID still return `401`.
6. **`@WithMockUser` passing only verifies policy with a simulated security context:** it must not be treated as evidence that real passwords/tokens were checked; the Basic 401/200 tests cover that part.

A single `403` check **does not prove** the right rule fired: CSRF can also produce a 403 before authorization. Therefore, a test pair with `with(csrf())` and without `csrf()` is needed to isolate the cause.

## 6. When Building MockMvc Manually: You Must Explicitly Integrate Spring Security

Not every project uses `@AutoConfigureMockMvc`. If using `WebApplicationContext` and a manual builder, the correct setup is:

~~~java
package com.example.securitytest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest
class ManualMockMvcSecurityTests {

    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setup() {
        mvc = webAppContextSetup(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void anonymousMustBeRejected() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

`SecurityMockMvcConfigurers.springSecurity()` attaches `FilterChainProxy` and sets up test security context support. This is the core difference compared to:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new ReportController(new ReportService()))
    .build();
~~~

The `standaloneSetup` snippet above is an **illustrative anti-pattern**, not to be used to claim security rules ran: it only instantiates the controller and service with `new`, without loading `SecurityFilterChain` beans or method security proxies. Calling `GET /api/reports/42` can return 200 even with no authentication info. If the goal is testing real security, use `webAppContextSetup(context).apply(springSecurity())` or the integrated Boot setup in section 5.

Do not arbitrarily mix `@AutoConfigureMockMvc` with manually building a second `MockMvc` assuming both share the same configuration. The instance injected by Spring Boot and the instance created by the builder may carry different filter lists.

## 7. Choosing the Right Identity Simulation Tool

| Identity supply method | What is tested | What is **not** proven |
| --- | --- | --- |
| `with(httpBasic("reader", "reader123"))` | Basic header and **real authentication pipeline** when the filter chain runs | Does not automatically prove a different Bearer/JWT pipeline |
| `@WithMockUser(authorities="REPORT_READ")` | Authorization based on a simulated `SecurityContext` | User exists in DB, password is correct, authentication provider runs |
| `with(user("tester").authorities(...))` | Request carries chosen principal/authorities | Token signature verification or real password verification |
| `@WithUserDetails("reader")` | Loads principal via `UserDetailsService` and sets `SecurityContext` | Does not automatically test password verification on each HTTP request |
| `with(jwt())` / `with(oauth2Login())` | Authorization scenarios with the corresponding simulated authentication | JWT signature, issuer, audience, JWKS retrieval, real OAuth redirect/handshake |
| Real `Authorization: Bearer <token>` header | Can test the full resource-server authentication chain if the app is genuinely configured | Does not imply network/TLS because MockMvc still uses mock requests |

`@WithMockUser` defaults to creating a user with `ROLE_USER`. For `hasAuthority("REPORT_READ")`, set `authorities="REPORT_READ"`; `roles="ADMIN"` normally produces the authority `ROLE_ADMIN`. Do not mix up `ROLE_ADMIN` and `ADMIN` in tests and blame the filter.

For HTTP Basic tests, `httpBasic` is better than `with(user(...))` when the requirement is **proving credential checking**. For Resource Servers, use `jwt()` to write authorization tests quickly, but add real token tests or `JwtDecoder`/validator tests to prove signatures and claims are validated properly.

## 8. A Common Trap: @WebMvcTest Does Not Necessarily Carry the Real Policy

`@WebMvcTest(ReportController.class)` only builds an MVC slice: the controller and selected web components, without loading all `@Service`/`@Configuration` beans like `@SpringBootTest`. When using slices:
- Spring Security on the classpath may activate default security, but default security **does not represent** the application's `SecurityFilterChain` if custom config is excluded from the slice.
- If the controller needs a service, provide `@MockitoBean` (Spring Boot 3.4+/Spring Framework 6.2+) or configure an appropriate collaborator.
- If you want to test specific rules, use `@Import(SecurityConfiguration.class)` and ensure all dependencies of that config are present; then verify no test filter chain overrides it.
- `@AutoConfigureMockMvc(addFilters=false)` can be useful for controller-only tests, but **never** use it for security integration tests.

*Illustrative* structure example of a slice test:

~~~java
@WebMvcTest(ReportController.class)
@Import(SecurityConfiguration.class)
class ReportControllerSliceTests {
    @Autowired MockMvc mvc;
    @MockitoBean ReportService service;

    // Subsequent HTTP tests must verify filters are actually added.
}
~~~

This snippet is placed separately to explain **slice scope**; to compile, add the right Boot 3.5 imports and full test definitions. `@WebMvcTest` alone does not prove method security on the real `ReportService`, because that bean is mocked. For the requirement "integrate the real filter chain along with real service security", prefer `@SpringBootTest` in section 5.

## 9. Diagnosing Unexpected 200/403/404 Tests

| Symptom | Common cause | How to verify/fix |
| --- | --- | --- |
| Anonymous calls protected endpoint yet test still returns 200 | MockMvc was built with `standaloneSetup` or `addFilters=false` | Switch to a context with `springSecurityFilterChain` and keep registration enabled; add anonymous = 401 test |
| Anonymous GET receives 302 instead of 401 | Application enables form login redirect | Check `AuthenticationEntryPoint`; test the right API chain (`httpBasic`/Bearer) or assert redirect per contract |
| POST with authorized user still gets 403 | Missing/invalid CSRF | Add `with(csrf())` in tests expected to succeed; keep invalid/missing CSRF tests separate |
| POST without CSRF still returns 201 | CSRF disabled, path excluded, or filter not running | Inspect `SecurityFilterChain` and CSRF matcher; make negative case mandatory |
| `with(user(...))` passes but wrong Basic password fails | User post-processor skips password verification | Use `httpBasic` to test real authentication; `user` only for authorization |
| `@PreAuthorize` does not block | Missing `@EnableMethodSecurity`, called via `this`/`new`, service is mocked | Call Spring bean via proxy, test method denial with appropriate role |
| Test sees 403 instead of 404 | Security blocks before MVC, or ERROR dispatch is blocked next | Create an authenticated test with sufficient permission; check dispatcher and rules |
| Using `hasRole("ADMIN")` but mock has authority `ADMIN` | `ROLE_` prefix mismatch | Use `roles("ADMIN")` or authority `ROLE_ADMIN` for `hasRole` rules |
| `@WebMvcTest` differs from production | Slice lacks beans/filter config or auto-config differs | Import required configuration; have at least one `@SpringBootTest` verifying integration |
| Tested `jwt()` and concluded signature is valid | `jwt()` only simulates authentication | Add real Bearer token tests or decoder/validator tests |
| Controller returns 200 even though service has deny rule | Method is mocked or self-invocation bypasses proxy | Avoid mocking the service in full security tests and call via Spring bean |
| Unit test does not see 401 because 403 is returned | CSRF can block before authentication on unsafe methods | Check anonymous GET first; POST always needs a separate CSRF test |

When debugging, you can temporarily enable logging:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Inspect which `SecurityFilterChain` matches the request, the authentication point, and the authorization point, but do not treat logs as the sole proof by default: **HTTP assertions on negative/positive inputs** are the durable check. `TRACE` logs can be huge; avoid leaving them enabled long in production.

## 10. Measuring the Right Scope of "Real Integration"

To evaluate test results, separate three layers:

1. **Security configuration**: Whether the application's `SecurityFilterChain` bean is created; which chain matches the request; which filters are activated. With multiple filter chains, request paths can select different chains (`securityMatcher` + `@Order`).
2. **Authentication/authorization behavior**: No credentials, invalid credentials, valid credentials lacking permission, sufficient permission; URL permissions and method permissions; special matchers such as dispatcher types.
3. **HTTP contract**: Body, `WWW-Authenticate` header, `401/403/404/201` codes, JSON serialization, and CSRF. A correct response can be produced for the wrong reason; therefore, tests must cross-check causal conditions.

For applications with multiple chains, write tests for **each major URL group**. For instance, `/api/**` and `/admin/**` may use different login mechanisms; a passing test on `/api/reports/42` does not prove `/admin/**` is safe. If security headers or session fixation policies are critical, add explicit header/cookie assertions.

**MockMvc limitations:** it does not fully simulate browser origin/cookie policies, proxy headers, TLS, or Servlet container networking. Login flows involving redirects, `SameSite`, real CORS, and token issuance/JWKS should have some additional live-server integration tests when risk warrants it.

## 11. Checklist Before Accepting a Test Suite

- [ ] `spring-boot-starter-test` and `spring-security-test` are on the test classpath, matching the Spring Security runtime version.
- [ ] Tests requiring full integration use `@SpringBootTest + @AutoConfigureMockMvc` or `webAppContextSetup(context).apply(springSecurity())`.
- [ ] `standaloneSetup` or `addFilters=false` is never used as proof of real security.
- [ ] Negative case exists: anonymous → **401/challenge matching configuration**.
- [ ] Negative case exists: wrong HTTP Basic password → **401**.
- [ ] Authenticated without authority → **403**, and with authority → **2xx**.
- [ ] For unsafe methods with CSRF: missing/invalid CSRF test → **403**, valid token and sufficient permission → **2xx**.
- [ ] Authorized user with non-existent business resource → **404**.
- [ ] If method security exists: test `@PreAuthorize` deny and allow via the real bean.
- [ ] Distinguish `@WithMockUser`/`with(user())` from real credential verification.
- [ ] With `@WebMvcTest`: confirm real config is imported, other dependencies are reasonably mocked, and do not extrapolate to full context.
- [ ] With OAuth2 Resource Server: test mocked authorization and token validator/signature separately.
- [ ] Include some live HTTP tests if requirements involve server/network/proxy/TLS/cookie/browser behavior.
- [ ] Tests re-run consistently without depending on shared data or ordering.

## Official Documentation

1. [Spring Security 6.5 — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/).
2. [Spring Security 6.5 — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html).
3. [Spring Security 6.5 — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html).
4. [Spring Security 6.5 — HTTP Basic MockMvc Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html).
5. [Spring Security 6.5 — CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html).
6. [Spring Security 6.5 — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html).
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
8. [Spring Framework 6.2 — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html).

A trustworthy HTTP security test suite must prove that **decisions actually pass through the right filter chain**, the user store/provider works, CSRF is checked, and method security is not bypassed. Negative tests (no identity, wrong password, missing permission, missing CSRF) are decisive in catching accidental filter bypasses.
