# MockMvc and Filter Chain Integration in Servlet Applications

> **Context:** Spring Boot 3.x, Spring Security 6.x, Spring MVC on the Servlet stack, Java 17+. This lesson belongs to the **Testing** group and focuses on the question: **does a MockMvc test actually traverse the Servlet Filter Chain and Spring Security `FilterChainProxy` just like the application's configuration?**

## 1. The problem to test

Suppose an API has a `SecurityFilterChain` requiring authentication for `/api/profile`, allowing only the ADMIN role on `/api/admin`, requiring the `MESSAGE_WRITE` authority on POST, and requiring a CSRF token on state-changing requests. The application also has a custom `OncePerRequestFilter` that writes a response header.

A test that only invokes the controller with `MockMvcBuilders.standaloneSetup(controller)` might see `GET /api/admin` return **200** for an anonymous caller. In production, that request must be rejected by Spring Security. A "green" test in that setup **does not prove security works**, because the test path had no real filters attached.

Conversely, when `@SpringBootTest` is combined with `@AutoConfigureMockMvc`, MockMvc typically integrates filters from the application context; a test might return **401**, **403**, or **302** before reaching the controller. That is usually a sign that filters executed, and you need to identify *which filter* decided the response.

This lesson aims for three practical outcomes:

1. Set up tests with the right scope of **Servlet filters, Spring Security filters, and MVC controllers**.
2. Test **anonymous callers, simulated users, real credentials, permissions, CSRF, and custom filters**; know which tests actually exercise real authentication.
3. Recognize behaviors MockMvc **cannot verify completely** because there is no real HTTP socket, reverse proxy, or servlet container.

## 2. Mechanism: how a request travels from client to Controller

A Spring MVC application running on Tomcat/Jetty/Undertow conceptually follows this path:

```text
Real HTTP client
    |
    v
Reverse proxy / ingress (if present)
    |
    v
HTTP connector + Servlet container
    |
    v
Servlet FilterChain
    |
    +-- Custom Servlet Filter: logging / tracing / CORS / ...
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
    |       |
    |       v
    |    FilterChainProxy
    |       |
    |       +-- select SecurityFilterChain matching request
    |       +-- security filters: context, CSRF,
    |           authentication, exception translation,
    |           authorization, ...
    |
    +-- Remaining Servlet filters (in actual order)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping / HandlerAdapter
    +-- Controller / service
    +-- Spring MVC HandlerExceptionResolver
    |
    v
HTTP response
```

This is a **diagram of responsibilities**, not an exact list of every filter or default ordering across all versions. Actual ordering depends on `FilterRegistrationBean`, `@Order`, container registration, `SecurityFilterChain` configuration, `DispatcherType`, and application extensions.

Three terms are often confused:

- **Servlet `FilterChain`:** the filter chain at the Servlet container level; a filter can run *before* a request reaches Spring MVC.
- **Spring Security `FilterChainProxy`:** itself exposed as a Servlet Filter, yet internally managing **one or more `SecurityFilterChain` beans** with their request matchers and security filters.
- **`DispatcherServlet`:** receives requests after filters allow them through, selects the MVC handler, and invokes the controller; this is where MVC `HandlerExceptionResolver`s operate.

When a filter writes a response directly instead of calling `chain.doFilter(...)`, the controller **does not execute**. When `CsrfFilter` rejects a POST, controller validation logic may not have run yet. When `AuthorizationFilter` blocks a URL, tests should assert both the expected status and that downstream actions did not execute.

### What does MockMvc preserve?

`MockMvc` creates `MockHttpServletRequest` and `MockHttpServletResponse`, sending requests through **Spring MVC test infrastructure**, including any filters attached to the builder. It opens no socket and does not require Tomcat to accept a real HTTP request.

Consequently:

- You can test controller mappings, JSON binding, MVC exception resolvers, filter invocations, statuses/headers/bodies, security matching, CSRF, Basic/form authentication, and authorization outcomes when the filter chain is integrated.
- You cannot claim you have tested HTTP connector byte parsing, header/request-line limits, TLS, reverse-proxy rewrites, container path decoding quirks, browser cookie policies, compression, or container error-page dispatches identically to a real server.
- Certain unhandled exceptions inside filters may **throw directly from `mvc.perform(...)`** in tests, rather than always turning into a 500 response via the embedded container's error page.

For container/proxy behaviors, add HTTP integration tests with `@SpringBootTest(webEnvironment = RANDOM_PORT)` or end-to-end tests through a production-like topology.

## 3. Three ways to initialize MockMvc and their coverage

| Initialization method | What gets loaded | Are Filters/Security automatically like the app? | When to use |
| --- | --- | --- | --- |
| `MockMvcBuilders.standaloneSetup(controller)` | The controller and MVC components you specify | **No**; filters must be added manually, no full `ApplicationContext` | Testing controller-specific mappings/binding |
| `@WebMvcTest(SomeController.class)` | MVC slice, slice-compatible beans, MockMvc | May auto-configure security, yet **does not automatically load all custom configs and services** | Controlled MVC/security contract tests with mocked collaborators |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Full Spring Boot application context (no socket started by default) | Usually includes context filters; `addFilters=true` by default | Testing controller + Servlet/Security filter flows close to app configuration |
| `@SpringBootTest(RANDOM_PORT)` + real HTTP client | Full context and real embedded server | Runs through the real Servlet container | Testing connector behavior, cookies, encoding, redirects, error dispatch |

In Spring Boot 3.x, `@AutoConfigureMockMvc(addFilters = true)` is the default. With `addFilters = false`, filters from the context are not registered on MockMvc. That can be useful for **pure MVC** tests, yet a test with `addFilters=false` **no longer proves 401/403/CSRF from the security filter chain**.

### Two common misconceptions

**"`@SpringBootTest` automatically creates a MockMvc bean for injection."** Not always. For Spring MVC, if you want Boot to auto-configure a `MockMvc` bean, add `@AutoConfigureMockMvc` (or build one manually).

**"`@WebMvcTest` is always identical to production."** No. The slice drops most services/repositories and may omit custom `@Configuration` outside the beans supported by the slice. If the test has a different security configuration from production, status codes can differ even when the controller is fine.

## 4. Required dependencies

A Spring Boot 3.3.x + Java 17+ example using Gradle, Spring MVC, Spring Security, and Spring Security Test:

`settings.gradle`:

```groovy
rootProject.name = 'mockmvc-filter-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
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
```

**Why is `spring-security-test` required?** It supplies `SecurityMockMvcRequestPostProcessors`, `SecurityMockMvcResultMatchers`, `SecurityMockMvcConfigurers.springSecurity()`, `@WithMockUser`, `@WithUserDetails`, `@WithAnonymousUser`, and extra security test utilities. `spring-boot-starter-test` brings in JUnit 5 and MockMvc-related Spring Test support, yet cannot replace Spring Security's specialized extensions.

The version in the example is a **baseline to reproduce Spring Boot 3.3 / Security 6 APIs**, not a recommendation to stay on an older patch in production. Real projects must follow maintained versions and their own security update policies. Do not mix Spring Boot 4.x test packages into Boot 3.x snippets; package imports changed across major versions.

## 5. Demo application with a Servlet filter and Spring Security

Create the following files, keeping the `com.example.mocksecurity` package:

```text
src/main/java/com/example/mocksecurity/
  MockSecurityApplication.java
  SecurityConfig.java
  TraceHeaderFilter.java
  DemoController.java

src/test/java/com/example/mocksecurity/
  FullFilterChainTest.java
```

### 5.1. Entry point — `MockSecurityApplication.java`

```java
package com.example.mocksecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockSecurityApplication.class, args);
    }
}
```

### 5.2. Security config — `SecurityConfig.java`

```java
package com.example.mocksecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/messages")
                    .hasAuthority("MESSAGE_WRITE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        // Do not disable CSRF: POST requires a token when CSRF is enabled.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        var writer = User.withUsername("writer")
            .password(encoder.encode("writer-pass"))
            .authorities("ROLE_USER", "MESSAGE_WRITE")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, writer, admin);
    }
}
```

Security rules in the example:

- `GET /public/ping`: `permitAll()` — no login required, though requests still pass through the security filter chain if attached.
- `GET /api/profile`: `anyRequest().authenticated()` — 401 when unauthenticated with HTTP Basic, 200 with valid credentials.
- `GET /api/admin`: requires `ROLE_ADMIN` — authenticated users holding only `ROLE_USER` typically receive 403.
- `POST /api/messages`: requires the exact `MESSAGE_WRITE` authority **and** a valid CSRF token. Having valid Basic credentials without a token is still rejected.
- Every remaining URL requires authentication to reach the MVC layer, even though the controller may return 404 if unmapped.

This is a **demo** policy. In-memory credentials are for local/testing use only. For stateless REST APIs accepting only Bearer tokens in headers, CSRF handling may differ; never copy CSRF enabling/disabling without evaluating your authentication model and browser usage.

### 5.3. Servlet Filter — `TraceHeaderFilter.java`

```java
package com.example.mocksecurity;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class TraceHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        response.setHeader("X-Test-Filter", "executed");
        filterChain.doFilter(request, response);
    }
}
```

`@Component` makes the filter a Spring bean so Boot registers it at the Servlet layer. `@Order` asks it to run very early. In this demo, because the filter runs before Spring Security, even responses blocked by security carry the `X-Test-Filter: executed` header.

**Do not register the filter twice:** if the class is already a `@Component` and Boot auto-registers it with the Servlet container, do not also create another `FilterRegistrationBean` or call `http.addFilterBefore(new TraceHeaderFilter(), ...)` without controlling registration. Running twice can make tests/headers/logs misleading.

**Note on `OncePerRequestFilter`:** the class name does not mean it executes only once across an entire network interaction. "Once" applies per request dispatch and relies on a filtered marker attribute; `ASYNC` and `ERROR` dispatches have dedicated conditions/overrides such as `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`.

### 5.4. Controller — `DemoController.java`

```java
package com.example.mocksecurity;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/profile")
    public String profile(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping(
        value = "/api/messages",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public String createMessage(@RequestBody MessageRequest request) {
        return "created:" + request.text();
    }

    public record MessageRequest(String text) {
    }
}
```

`@PreAuthorize` is omitted in this demo because the lesson focuses on **Servlet/Spring Security request filters**. Real applications may combine method security and object-level authorization in services; MockMvc tests must be complemented with direct service tests or appropriate integration tests when such policies exist.

The example also does not persist real data. A `created:hello` response only proves the controller endpoint ran after all security checks passed.

## 6. Integrating the full filter chain with @SpringBootTest + @AutoConfigureMockMvc

This is the core test of the lesson. File `FullFilterChainTest.java`:

```java
package com.example.mocksecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FullFilterChainTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicEndpointPassesThroughCustomServletFilter() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"))
            .andExpect(header().string("X-Test-Filter", "executed"));
    }

    @Test
    void anonymousUserIsRejectedBeforePrivateController() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("X-Test-Filter", "executed"))
            .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void actualHttpBasicCredentialsAreValidatedBySecurity() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:reader"));
    }

    @Test
    void wrongBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotOpenAdminRoute() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "test-admin", roles = "ADMIN")
    void mockAdminMayAccessAdminRoute() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void requestPostProcessorCanSupplyMockPrincipal() throws Exception {
        mvc.perform(get("/api/profile")
                .with(user("sample-user").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:sample-user"));
    }

    @Test
    void writerWithValidCsrfAndAuthorityCanPost() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:hello"));
    }

    @Test
    void writerWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerWithInvalidCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithCsrfStillLacksWriteAuthority() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }
}
```

In the test file, there is no need to add `@ExtendWith(SpringExtension.class)` because `@SpringBootTest` already integrates Spring Test with JUnit Jupiter. `@AutoConfigureMockMvc` registers the MockMvc setup matching the Boot context; **do not construct a separate `MockMvcBuilders.standaloneSetup(...)` inside this test**, as it would discard the filter integration under verification.

### Why is each test valuable?

| Test | What it proves | Limitations |
| --- | --- | --- |
| `publicEndpointPassesThroughCustomServletFilter` | Custom filter runs even on public routes | The header does not prove every other filter is right; security tests are still needed. |
| `anonymousUserIsRejectedBeforePrivateController` | Security chain blocks login-required routes | Does not test the credential provider. |
| `actualHttpBasicCredentialsAreValidatedBySecurity` | Basic header passes through the authentication mechanism and demo user store | Does not prove production passwords or an external IdP. |
| `wrongBasicPasswordReturns401` | Invalid credentials are truly rejected | Does not test rate limiting or brute-force protections. |
| `authenticatedReaderCannotOpenAdminRoute` | Route-level authorization rejects USER | Does not check per-record permissions. |
| `mockAdminMayAccessAdminRoute` | Authority rule with a mock principal | Does not prove account `test-admin` exists. |
| `writerWithValidCsrfAndAuthorityCanPost` | Having both authority and token lets the controller run | Does not test DB persistence or proxy/container. |
| `writerWithoutCsrfIsRejected` | CSRF filter is active | Must not be used to conclude the user lacks permission. |
| `readerWithCsrfStillLacksWriteAuthority` | Removes CSRF noise to test actual authorization logic | Does not replace business checks inside services. |

The controller bodies `pong`, `hello:reader`, `admin`, and `created:hello` are fixed strings, so `content().string(...)` outcomes are deterministic. Status codes may differ in apps with form login or custom exception handlers; for the **HTTP Basic demo configuration above**, 401/403/201 are the expected outcomes to verify.

### How to run

```bash
# If the project already has a Gradle wrapper:
./gradlew test

# Start the application to test over real HTTP:
./gradlew bootRun
```

If a newly created project lacks a wrapper, use `gradle test`/`gradle bootRun` with a compatible Gradle version or generate the wrapper per project conventions. This is a **Spring Boot application**; do not compile individual files with plain `javac` because the classpath depends on Spring/Security/JUnit.

When tests run, Gradle/JUnit outputs summary results without a single canonical stdout string to match. The HTTP status/header/body assertions are the actual test evidence.

## 7. Distinguishing mock authentication from real authentication

Spring Security Test provides several tools. They answer **different questions**.

### 7.1. `.with(user(...))` — creates a SecurityContext for the request

```java
mvc.perform(get("/api/profile")
        .with(user("alice").roles("USER")))
    .andExpect(status().isOk())
    .andExpect(content().string("hello:alice"));
```

`user(...)` is a `RequestPostProcessor`: it assigns a principal and authorities to the test request via Spring Security Test when properly integrated. User `alice` **does not need to exist in a database or `UserDetailsService`**.

Use this when focusing on rules like `hasRole`, `hasAuthority`, access control, and the principal data received by controllers/services. This is **not a password test** or a real JWT token test.

`roles("USER")` generates `ROLE_USER`; `authorities("MESSAGE_WRITE")` keeps the literal name. Do not write `roles("ROLE_USER")` when you mean a simple USER role, as that can cause a prefix mismatch.

### 7.2. `@WithMockUser` — creates an authentication context for a test

```java
@Test
@WithMockUser(username = "report-viewer", roles = {"USER"})
void mockPrincipalExample() throws Exception {
    mvc.perform(get("/api/profile"))
        .andExpect(status().isOk())
        .andExpect(content().string("hello:report-viewer"));
}
```

This annotation belongs to `spring-security-test` and is handled by `WithSecurityContextTestExecutionListener`; it sets up the security context for the test and clears it afterward. Like `with(user(...))`, it does not authenticate passwords through `AuthenticationManager`.

For method security needing a specialized principal, `@WithUserDetails` can load a real user from `UserDetailsService`, and custom `@WithSecurityContext` supports arbitrary principal/token types. Never put `@WithMockUser` at the class level for an **entire suite** if some tests require anonymous access; doing so turns 401 tests into 200 and hides bugs.

### 7.3. `.with(httpBasic(...))` — sends a real credentials header to the filter

```java
mvc.perform(get("/api/profile")
        .with(httpBasic("reader", "reader-pass")))
    .andExpect(status().isOk());

mvc.perform(get("/api/profile")
        .with(httpBasic("reader", "bad-pass")))
    .andExpect(status().isUnauthorized());
```

The `httpBasic` post-processor only creates an HTTP Basic header; it **does not grant a logged-in user by itself**. Only when the full Spring Security filter chain includes `BasicAuthenticationFilter` and an appropriate `AuthenticationManager` are credentials verified. This is a better way to prove the Basic authentication path than `with(user(...))`.

However, to test session form login, OAuth2 redirects, Bearer JWT, or SAML, you must use the requests/handlers for that specific mechanism; do not treat Basic as a proxy for every authentication type.

### 7.4. `csrf()` — only for CSRF testing, not "admin privilege"

```java
mvc.perform(post("/api/messages")
        .with(user("writer").authorities("MESSAGE_WRITE"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"ok\"}"))
    .andExpect(status().isCreated());
```

`csrf()` supplies a valid token for the test request; `csrf().asHeader()` places it in a header, and `csrf().useInvalidToken()` intentionally supplies a bad token. It adds no authorities or authentication. Nor does it **prove** a production browser/SPA sends cookies and CSRF tokens properly; live HTTP tests verify that.

In practice, with cookie sessions and browsers, CSRF is an essential control. If a POST test hits 403, try supplying a valid token first to separate **CSRF failure** from **authorization failure**, instead of blindly removing `csrf()` or calling `csrf.disable()`.

## 8. Manual MockMvc builder: placing springSecurity() in the right spot

When you prefer building MockMvc manually from `WebApplicationContext` instead of `@AutoConfigureMockMvc`, Spring Security Test provides:

```java
package com.example.mocksecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class ManualMockMvcWithSecurityTest {

    @Autowired
    private WebApplicationContext applicationContext;

    private MockMvc mvc;

    @BeforeEach
    void createMvc() {
        mvc = MockMvcBuilders.webAppContextSetup(applicationContext)
            .addFilters(new TraceHeaderFilter())
            .apply(springSecurity())
            .build();
    }

    @Test
    void customFilterAndSecurityAreBothInvoked() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("X-Test-Filter", "executed"));
    }
}
```

`springSecurity()` attaches Spring Security's `FilterChainProxy` and the test support needed for `with(user(...))` and `@WithMockUser`. `addFilters(new TraceHeaderFilter())` explicitly adds the **custom Servlet filter** so this test covers both. A manual builder **does not automatically include** every servlet filter registered by Boot in production; when multiple filters, orders, and dispatcher types matter, `@AutoConfigureMockMvc` stays closer to Boot's runtime behavior.

**The setup above is an alternative** to `@SpringBootTest + @AutoConfigureMockMvc` shown in section 6. Do not add the same `FilterChainProxy` twice to the builder or re-add a Servlet filter already registered by the builder, as running a filter twice can corrupt test outcomes.

### Calling standaloneSetup

```java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new DemoController())
    .build();
```

This builds a standalone controller without `FilterChainProxy`. As a result, `GET /api/admin` can return **200** in an unsecured test even though production must return 401/403. That is a **property of the test scope**, not a production bug finding.

`standaloneSetup` remains valuable for unit-style MVC tests: mappings, body serialization, status codes, or manually registered exception resolvers. Just never cite standalone results as proof that security rules protect the endpoint.

## 9. `@WebMvcTest` slice tests: fast, yet you must know what is loaded

`@WebMvcTest(DemoController.class)` loads only a slice of the web layer—typically controllers, controller advice, MVC converters, selected filters, security auto-configuration, and MockMvc. **Normal service/repository beans** are not loaded automatically; mock required collaborators or import the relevant configuration.

Slice test example for the demo controller with no service dependencies:

```java
package com.example.mocksecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DemoController.class)
@Import(SecurityConfig.class)
class DemoControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "admin-in-slice", roles = "ADMIN")
    void adminRuleIsExercisedInSlice() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }
}
```

`@Import(SecurityConfig.class)` instructs the slice to use the specified security configuration rather than relying on an implicit setup that might differ from the app. In real systems, inspect which dependencies, exception handlers, conversions, servlet filters, and security rules the slice excludes; add mocks and imports deliberately. Avoid importing every service just to turn a slice into an ambiguous integration test.

Sometimes a `@WebMvcTest` returns 401 when you only wanted to check a JSON body; two sensible options exist:

- Keep filters/security enabled and attach an appropriate principal to the request (e.g., `with(user(...))`) if the test should verify security behavior too.
- Separate an MVC-only test with no filters, clearly named and scoped as **testing MVC behavior only**, while maintaining a separate full-chain test to guarantee authorization.

Never react by disabling Security across the whole test suite and still claiming every endpoint is protected.

## 10. Testing form login, redirects, and sessions beyond Basic

The demo app in section 5 configures **HTTP Basic** and has not enabled `formLogin`. Therefore, the example below applies **only after the application is configured for form login** with `http.formLogin(Customizer.withDefaults())` and a matching `UserDetailsService`.

Spring Security Test provides the `formLogin()` request builder. With default form login, it sends `POST /login` with `username`, `password`, and a **valid CSRF token**.

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;

// Place inside @SpringBootTest + @AutoConfigureMockMvc with formLogin:
mvc.perform(formLogin().user("reader").password("reader-pass"))
    .andExpect(authenticated().withUsername("reader"));

mvc.perform(formLogin().user("reader").password("wrong"))
    .andExpect(unauthenticated());
```

This is a **separate illustration**; do not paste these two lines directly into `FullFilterChainTest` for the HTTP Basic-only config. When login uses a path other than `/login` or custom parameter names, use the matching overloads such as `formLogin("/auth").user("u", "reader").password("p", "reader-pass")`.

### Testing SavedRequest and cookies/sessions

`@WithMockUser` only creates a mock principal in the test; it **does not prove** that a really logged-in user is saved in the session and continues after a redirect. For form login and session-based authentication, tests should:

1. Request a protected URL while unauthenticated and verify the redirect to login.
2. Submit login with a CSRF token.
3. Reuse the same `MockHttpSession`/cookies across MockMvc requests.
4. Request the protected URL again and verify the authenticated principal.
5. Send logout POST with valid CSRF, then verify the private URL is no longer accessible using the old session.

When testing sessions, each `mvc.perform(...)` creates a fresh request. Do not assume cookies/sessions persist automatically across calls like in a browser; pass `MockHttpSession` or use session-management test APIs explicitly. For redirects, `status().is3xxRedirection()` and `redirectedUrl(...)` verify the redirect response; MockMvc **does not follow redirects automatically** like a browser.

For OAuth2/OIDC login, HTTP Basic, or Bearer JWT, replace context/session setup and assertions with the matching test support. `formLogin()` only verifies the form login mechanism.

## 11. When an application has multiple SecurityFilterChains

Spring Security can define multiple `SecurityFilterChain` beans and select one based on `RequestMatcher`. Example:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll()
        );
    return http.build();
}
```

This is an **alternative example** to the `SecurityFilterChain` bean in section 5—do not put three overlapping beans into the same demo. Import `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer` in the config class.

Meaning:

- The first chain applies only to `/api/**`; `@Order(1)` is evaluated first.
- The second chain acts as a fallback for remaining requests.
- Each request normally passes through the **first matching `SecurityFilterChain`** in `FilterChainProxy`.
- `anyRequest().authenticated()` in the first chain **does not** protect paths outside `/api/**`.
- For login/logout endpoints, ensure their paths fall inside the matcher of the right chain; otherwise filters may never process them.

Tests must send representative requests **across every `securityMatcher` boundary**: `/api/profile`, `/public/ping`, fallback paths, and look-alike routes outside the matcher. A test verifying only `GET /api/profile` does not prove the web chain is configured properly.

## 12. Proving a custom filter runs and at which layer

An `X-Test-Filter` response header is easy to observe, yet investigating complex issues requires checking:

- Is the filter registered as a **Servlet Filter bean** or added with `http.addFilterBefore/After/At(...)` inside **a `SecurityFilterChain`**?
- Is any filter registered **twice** at both layers?
- Which dispatcher type—`REQUEST`, `FORWARD`, `ERROR`, or `ASYNC`—is involved?
- How do `@Order` or `FilterRegistrationBean.setOrder(...)` position it relative to `DelegatingFilterProxy`?
- Does the filter call `filterChain.doFilter(...)`? If it writes an early response, do downstream filters/handlers skip running?
- Does the test setup add filters automatically or register only one filter manually?

**Example blocking a request before the controller** (illustrated in another `OncePerRequestFilter`, not added directly to `DemoController`):

```java
if ("blocked".equals(request.getHeader("X-Demo-Mode"))) {
    response.sendError(HttpServletResponse.SC_BAD_REQUEST);
    return;
}
filterChain.doFilter(request, response);
```

If the filter is wired into MockMvc, a request with `X-Demo-Mode: blocked` will not invoke the controller. However, details of `sendError` handling by a real container and `ERROR` dispatch can differ from MockMvc. If a test only observes status 400, verify which filter blocked it instead of assuming MVC's `@ControllerAdvice` handled it.

**Do not catch every `RuntimeException` from `chain.doFilter(...)` and force all of them to 400.** Doing so can mask Security exceptions, application bugs, and data errors, causing wrong status codes or double-written responses.

## 13. Confusing interactions among CSRF, methods, roles, and statuses

### 13.1. Missing CSRF often masks authorization errors

With the demo configuration:

```text
POST /api/messages + writer valid Basic + no CSRF
    -> 403 from CSRF check

POST /api/messages + reader valid Basic + valid CSRF
    -> 403 due to missing MESSAGE_WRITE

POST /api/messages + writer valid Basic + valid CSRF
    -> 201 from controller

GET /api/profile + reader valid Basic
    -> 200

GET /api/profile + anonymous
    -> 401 + HTTP Basic challenge
```

Exact security filter ordering depends on configuration, yet in the demo, missing CSRF can block a POST before controller authorization rules run. Thus, seeing only "403" does not tell you **whether the cause is missing permission or CSRF**. Write two separate tests as in section 6 to isolate the cause.

### 13.2. Distinguishing roles and authorities

- `hasRole("ADMIN")` matches the `ROLE_ADMIN` authority by default.
- `hasAuthority("MESSAGE_WRITE")` matches the exact string `MESSAGE_WRITE`.
- `user("alice").roles("ADMIN")` creates a role with the conventional prefix.
- `user("alice").authorities("MESSAGE_WRITE")` creates a literal authority.

If a test with `@WithMockUser(roles="ADMIN")` returns 200 while a real user from JWT/DB still gets 403, the mapping from claims/roles/authorities to `GrantedAuthority` may be wrong. Tests with mock principals cannot prove a real converter or identity provider; add tests for credential/token-to-authority mapping.

### 13.3. Form login may return 302 instead of 401

When an app enables form login and uses `LoginUrlAuthenticationEntryPoint`, an anonymous request to a protected resource usually **redirects 302** to the login page. With an HTTP Basic entry point, that request normally returns **401** and `WWW-Authenticate`. Therefore, never copy 401 assertions from a Basic demo into a browser form-login app without checking the configuration.

### 13.4. Method-level security

If a service uses `@PreAuthorize`, a `@WebMvcTest` may not load the real service/proxy; you need separate method-security or full-context tests. `@EnableMethodSecurity` must be enabled. Also watch out for Spring proxy self-invocation: `this.protectedMethod()` inside the same object can bypass the interceptor. A MockMvc test against a controller with a mocked service will not catch this bug.

## 14. Handling async dispatch, ERROR dispatch, and simulation limits

### 14.1. Async controllers

Spring MVC supports controllers returning `Callable` or `DeferredResult`. With MockMvc, the initial `perform` starts async processing, and `asyncDispatch` is required to inspect the final response:

```java
// The following snippet assumes the application has
// GET /api/async returning Callable<String>.
MvcResult result = mvc.perform(get("/api/async")
        .with(user("reader").roles("USER")))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(content().string("done"));
```

Corresponding static imports:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
```

This is a **snippet depending on `/api/async`**; it is not in the initial `DemoController`. To try it standalone, add the following method to the controller:

```java
@GetMapping("/api/async")
public java.util.concurrent.Callable<String> async() {
    return () -> "done";
}
```

When running async, verify the security context propagates properly to the async execution stage; do not rely blindly on `ThreadLocal` inside worker threads. Which filters re-run on `ASYNC` dispatch depends on registration/`OncePerRequestFilter`. A header test on the initial request does not prove the filter runs on every dispatch.

### 14.2. ERROR dispatch and filter exceptions

Spring Boot provides `/error` handling backed by container error pages. When an exception escapes a filter, MockMvc **does not fully reproduce** Tomcat's error dispatch. Therefore:

- If `mvc.perform(...)` throws an exception, do not assume production returns a response body matching that exception.
- If you truly need to verify `BasicErrorController`, `DispatcherType.ERROR`, headers after `sendError`, or filters receiving ERROR dispatches, run an embedded server on a random port with a real HTTP client.
- `@ControllerAdvice` tests only verify exceptions within the MVC lifecycle; exceptions thrown in filters before `DispatcherServlet` **do not automatically** enter MVC exception resolvers.

### 14.3. URL encoding and container firewalls

MockMvc lets tests build requests with paths configured directly; real HTTP servers and proxies may normalize/decode encoded slashes, `..`, semicolons, or backslashes before Spring Security sees the request. Using MockMvc to test `HttpFirewall` and matchers at the Spring layer is useful, yet do not conclude production connectors process URIs "identically."

If your threat model involves encoded paths, request smuggling, HTTP/2, transfer encoding, header sizes, or TLS, add tests through the **real HTTP path** instead of relying solely on `MockHttpServletRequest`.

## 15. Complementing MockMvc with HTTP integration tests

When you need to test the embedded servlet container, Spring Boot provides:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpIntegrationTest {
    // Use a real HTTP client to send requests to the assigned port.
    // Verify status, redirects, cookies, headers, and error dispatch.
}
```

This is an **annotation template**, not a complete test file. Use `@LocalServerPort` to read the actual port and send requests with `RestClient`, `TestRestTemplate`, or an HTTP client library in the test class. Pick an HTTP client matching your dependencies and Spring Boot version; do not assume every client retains sessions/cookies automatically.

With the `DemoController` from section 5 running locally via `bootRun`, you can test with curl:

```bash
# 200 + pong
curl -i http://localhost:8080/public/ping

# 401 + WWW-Authenticate (HTTP Basic)
curl -i http://localhost:8080/api/profile

# 200 + hello:reader
curl -i -u reader:reader-pass http://localhost:8080/api/profile

# 403 because reader lacks ROLE_ADMIN
curl -i -u reader:reader-pass http://localhost:8080/api/admin
```

POST/CSRF requests over real HTTP need a **valid CSRF token** from the application's token-issuance mechanism; `.with(csrf())` is a MockMvc test tool, not something curl adds automatically. The demo does not define a token-issuance endpoint because the lesson focuses on MockMvc; in real browser/SPA apps, add and test a matching CSRF token flow.

## 16. Reading test results for accurate diagnosis

An investigation checklist when tests fail:

| Symptom | Likely causes to inspect | Evidence to gather |
| --- | --- | --- |
| Every protected GET returns 200 for anonymous | MockMvc lacks Security `FilterChainProxy`, `addFilters=false`, or overly broad rule | Dedicated 401 test, builder config, `springSecurityFilterChain` bean |
| Every POST returns 403 | Missing/invalid CSRF token, or deny rule | Compare POST with and without `with(csrf())` for the same principal |
| `@WithMockUser` test passes yet real Basic gets 401 | Mock principal skips authentication, wrong username/password, or broken password encoder | `httpBasic` tests with valid and invalid credentials |
| Expected 401 but received 302 | Form login/entry point redirect | `Location` header, active `SecurityFilterChain` |
| Custom filter header is missing | Filter not registered in MockMvc, wrong path/dispatcher type, ordering/response rewrite | Inspect filter registration and test public/protected paths separately |
| Controller advice does not run on filter errors | Exception thrown before `DispatcherServlet` | Stack trace origin, filter/ERROR dispatch |
| Slice test fails with missing service bean | `@WebMvcTest` does not load most service beans | Mock collaborator or switch to full-context test |
| MockMvc is green yet unusual paths are blocked in production | Connector/proxy decodes URIs differently from simulation | Live raw-path requests through the actual proxy/connector |
| Session disappears between two `perform` calls | Forgot to pass `MockHttpSession` back, or test never ran real login | Inspect session/cookies and login filter handler |
| A filter executes twice | Registered as both Servlet Filter and Security filter, multiple dispatches, or added twice to MockMvc | List filter registrations, dispatch types, and call traces |

When you need to inspect request details in a test, use `andDo(print())` on the test under investigation:

```java
mvc.perform(get("/api/profile"))
    .andDo(print())
    .andExpect(status().isUnauthorized());
```

Import:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
```

It prints MockMvc-level request, handler, status, headers, and body details. Never print passwords, cookies, bearer tokens, or real PII into CI logs. For detailed security-chain tracing, enable appropriate logging on `org.springframework.security` in the **test environment** only when needed, then turn off verbose logging.

### Note on `@MockitoBean`/`@MockBean`

Newer Spring Framework versions introduce `@MockitoBean` to replace beans in a test context, whereas older Spring Boot 3.3 examples commonly use `@MockBean`. If a service/repository bean is mocked and returns empty data by default, a controller test may fail with 404 even after security permits the request. Configure mock return values properly so tests distinguish business errors from security failures. Never mock `SecurityFilterChain` or `AuthenticationManager` carelessly and claim the test proves real authentication.

## 17. Mistakes that produce "false-green" security tests

1. **Using only `standaloneSetup` to prove authorization:** the builder has no full filters unless manually added.
2. **Setting `addFilters = false` to "fix" 401/403:** the test drops the exact layer it is meant to verify.
3. **Putting `@WithMockUser` on the whole class and then testing anonymous:** the anonymous test actually runs with a mock user.
4. **Using `with(user(...))` to claim passwords/JWTs are validated:** this tool only creates a test principal.
5. **Forgetting `with(csrf())` on POST/PUT/DELETE:** tests may stop at CSRF before reaching functional authorization rules.
6. **Asserting only status 403:** hides whether the cause is CSRF, missing authority, or a deny rule; test each cause separately.
7. **Not verifying custom Servlet filter registration:** controller success does not mean audit/header/filters ran.
8. **Registering a filter twice:** test diverges from production or triggers duplicate side effects.
9. **Assuming `@WebMvcTest` pulls in every config/service:** the slice excludes many beans, including custom `@Configuration`.
10. **Not testing routes outside `securityMatcher`:** some URLs may skip the chain you think covers them.
11. **Mistaking `MockMvc` for a real HTTP server:** misses URL parsing, TLS, container error pages, and reverse proxies.
12. **Trusting 200 status as proof real requests are protected:** if filters are bypassed, 200 only reflects the controller.
13. **Not testing wrong credentials or non-existent principals:** passing with a mock principal does not prove the authentication provider.
14. **Skipping side-effect checks after denial:** a poorly designed handler/service can mutate data before checking permissions; for update/delete cases verify the DB did not change.
15. **Writing tests that pass by hardcoding mock security responses:** may fail to verify the real filter chain execution.
16. **Not separating test layers:** maintain focused MVC tests, filter-chain tests, and live HTTP tests so failures pinpoint the exact root cause.

## 18. Completion criteria for Filter Chain testing

- [ ] Tests match the app type: Servlet MVC (not confused with reactive WebFlux/`WebTestClient`).
- [ ] `spring-security-test` is declared in test scope.
- [ ] `@SpringBootTest` + `@AutoConfigureMockMvc` runs with `addFilters=true` when the full chain is needed.
- [ ] Anonymous GET to protected routes is tested and verified for 401/redirect per active entry point.
- [ ] Valid/invalid credentials are tested through the real authentication filter for the app's mechanism.
- [ ] Authenticated-without-permission cases are tested and distinguished from unauthenticated cases.
- [ ] Requests are tested with a valid CSRF token and with missing/invalid tokens.
- [ ] Custom Servlet filters are tested: headers/behavior are observed both when controllers run and when Security blocks.
- [ ] Routes outside or spanning boundaries between multiple `securityMatcher`s are verified.
- [ ] Blocked requests are verified not to execute handlers/business logic, especially for mutating actions.
- [ ] Controller advice is tested separately, with awareness that filter exceptions do not automatically hit MVC resolvers.
- [ ] Real HTTP tests exist when needed to prove container, proxy, URI encoding, cookies, redirects, or error dispatch.
- [ ] `@WithMockUser` is never used to substitute for real authentication tests.
- [ ] `standaloneSetup` or `addFilters=false` is never cited as proof of the full security chain.
- [ ] Bean configuration and packages in tests have been checked; no unexpected filter duplication occurs.

### Self-check questions

1. Why can `MockMvcBuilders.standaloneSetup(new DemoController())` return 200 for `/api/admin` when production returns 401/403?
2. What security evidence is lost with `@AutoConfigureMockMvc(addFilters=false)`?
3. What does `springSecurity()` do when used with `MockMvcBuilders.webAppContextSetup(...)`?
4. What is the difference between `with(user("reader"))` and `with(httpBasic("reader","reader-pass"))`?
5. Why can a POST without a CSRF token return 403 even when `writer` has `MESSAGE_WRITE`?
6. Does `@WithMockUser(roles="ADMIN")` prove an admin account exists in the database?
7. Why can `@WebMvcTest` yield different results from `@SpringBootTest` for the same controller?
8. What extra test is needed if a reverse proxy/container handles encoded URLs differently from MockMvc?
9. Does an exception thrown inside a Servlet Filter automatically trigger `@RestControllerAdvice`?
10. Why must you test URLs across multiple `securityMatcher`s?
11. Is a `OncePerRequestFilter` guaranteed to run only once across REQUEST, ASYNC, and ERROR dispatches?
12. How do you verify that a blocked request did not modify data?

**Hints:** (1) standalone setup registers no security filters; (2) authorization, CSRF, and custom filter processing; (3) registers `FilterChainProxy` and security test integration; (4) mock principal vs sending a Basic header for filter authentication; (5) CSRF filter rejects earlier; (6) no; (7) slice differs from full context; (8) live HTTP test through the real server/proxy; (9) not automatically; (10) chain selection depends on matchers; (11) depends on dispatcher types and filter behavior; (12) assert DB state/side effects alongside HTTP status.

## Official documentation by version

- Spring Security 6.5 — Setting up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — Running a Test as a User: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Testing Form Login: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Framework — MockMvc Setup Options: https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Security — Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
