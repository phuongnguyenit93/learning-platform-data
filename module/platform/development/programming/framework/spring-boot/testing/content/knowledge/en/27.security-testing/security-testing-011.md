# Limitations of Disabling Filters to Make Tests Pass

## 1. Does a green test actually prove security works?

A Spring Boot test sends `POST /api/items` through `MockMvc`, receives `403 Forbidden`, and the developer changes the annotation to `@AutoConfigureMockMvc(addFilters = false)`. Now the response is `201 Created` and CI turns green. However, that change stops registering Servlet Filters from the `ApplicationContext` into `MockMvc`. If the system uses Spring Security on the Servlet stack, request-level authentication, authorization, CSRF, and security headers are normally enforced through `FilterChainProxy`, a Filter that may now have been bypassed.

**Conclusion:** a passing result on a MockMvc path that skips filters **does not prove** the same request is allowed through a real HTTP server. It can isolate a controller-only test, yet it is never how you fix a failing security test.

This lesson focuses on the **limitations of disabling filters just to make tests pass**. It uses Java 17+, Spring Boot 3.5.x, Spring Security 6.x, Spring MVC, and JUnit Jupiter. A complete example provides a REST application with a security policy, **9 tests keeping filters enabled**, and **7 control tests** where MockMvc bypasses filters while the real HTTP server still enforces protection. On Spring Boot 4.x, imports and starter packages may change; check documentation for your major version.

You will learn to distinguish:

- MockMvc context-filter registration vs the Servlet filter chain on an HTTP server.
- How `@WithMockUser`, `user(...)`, and `csrf()` differ from `addFilters=false`.
- Which security contracts silently disappear from tests: 401, 403, roles, CSRF, response headers, and custom filters.
- Boundaries of method security, MVC interceptors, and Bean Validation that can keep working.
- When controller-only bypass is reasonable vs when filters are mandatory.
- How to test custom `SecurityFilterChain`, CORS, JWT/OAuth2, tenant context, and CI runs.
- The rule against altering production security merely to appease a broken test fixture.

## 2. What boundaries does an HTTP request cross?

```text
REAL HTTP CLIENT
      |
      v
Servlet container
      |
      +-- Registered servlet filter chain
      |      |
      |      +-- Spring Security FilterChainProxy
      |      |      - security context/authentication
      |      |      - CSRF
      |      |      - request authorization
      |      |      - exception translation
      |      |      - security response headers
      |      |
      |      +-- Custom servlet filters
      |             - tenant/correlation/audit/CORS...
      |
      v
DispatcherServlet
      |
      +-- MVC HandlerInterceptor / argument resolvers
      |
      v
Controller -> Spring service -> repository
```

This diagram is a conceptual model; the actual filters, order, and implementations depend on Spring Security and application configuration. In Spring Boot auto-configured MockMvc, filters from the `ApplicationContext` are added to MockMvc when `addFilters=true` (the default). Switching it to `false` omits registering those context filters on MockMvc.

```text
@SpringBootTest + @AutoConfigureMockMvc
      |
      v
    MockMvc
      |
      +-- Context filters (default true)
      +-- Spring Security FilterChainProxy
      |
      v
 DispatcherServlet -> Controller

@SpringBootTest + @AutoConfigureMockMvc(addFilters=false)
      |
      v
    MockMvc
      |
      +-- No context-filter registration by Boot builder
      |
      v
 DispatcherServlet -> Controller
```

**Easy to miss:** a Spring Boot test using `RANDOM_PORT` can both inject `MockMvc` and start a real server. The `addFilters=false` flag applies to **`MockMvc`**, without turning real-server requests into filter-bypassing requests.

## 3. What exactly does @AutoConfigureMockMvc(addFilters=false) do?

Per the Spring Boot 3.5 Javadoc, `addFilters` controls whether filters from the `ApplicationContext` are registered with `MockMvc`; the default is **true**.

| Component | Affected by `addFilters=false`? | Notes |
|---|---|---|
| Boot auto-configured `MockMvc` | **Yes** | Skips registering context filters |
| Spring Security servlet chain on MockMvc path | **Typically yes** | `FilterChainProxy` is not executed along that path |
| Real HTTP server on `RANDOM_PORT` | **Not by this flag** | Servlet container still registers filters normally |
| `SecurityFilterChain` bean in Spring context | Not necessarily | Bean can still exist even when MockMvc skips it |
| `@PreAuthorize` on Spring-managed service | Not directly | Method-security AOP still runs if enabled and called via proxy |
| MVC `HandlerInterceptor` | Not by default | Distinct from Servlet Filters |
| `@Valid`/Bean Validation at MVC layer | Not directly | Still validates DTOs |
| `@ControllerAdvice` | Not directly | `HandlerExceptionResolver` can still handle exceptions |
| Database row-level security | Not directly | Enforced at the database resource |
| WebFlux `WebFilter` | Not part of this API | This is a Servlet MockMvc setting |
| Manually built standalone `MockMvc` | Depends on manual setup | Cannot infer from Boot annotations for every instance |

A test still returning 403 after `addFilters=false` does not prove security filters ran; a service `@PreAuthorize` or a separate interceptor might have blocked it. Conversely, if a controller relies solely on URL authorization in the filter chain, the test can return 200 to anonymous callers.

### 3.1. Do not confuse different options

- `addFilters=false`: changes **MockMvc filter registration**, potentially skipping custom Servlet Filters too.
- `authorizeHttpRequests(...permitAll())`: changes the **URL authorization rule**; the filter chain remains active and may still enforce CSRF and security headers.
- `csrf.disable()`: changes CSRF policy; does not remove authentication/authorization.
- `@WithMockUser`: fakes an authenticated principal in the test security context, yet authorization is still checked when the chain is properly wired.
- `user("name").roles("USER")`: request-specific test identity.
- `csrf()`: supplies a valid test CSRF token.
- Excluding `SecurityAutoConfiguration`: changes Spring context beans/config, not equivalent to a MockMvc flag.
- Mocking `SecurityFilterChain` or `FilterChainProxy`: replaces the security pipeline itself; requires careful scope evaluation, never a “quick fix”.

**Never weaken a production guard just to keep tests returning 2xx.** First determine whether the test fixture is wrong or the production policy itself has a bug.

## 4. Why does bypassing filters produce false positives?

### 4.1. Authentication

An endpoint meant for authenticated users must reject unauthenticated requests. In the HTTP Basic demo, the expected result is 401. With form login it can be a 302 redirect, and with Bearer tokens/resource servers it can be 401 with `WWW-Authenticate`. Removing security filters from MockMvc lets the controller run and return 200, hiding broken authentication configs or rules.

### 4.2. Authorization

An endpoint `/api/admin/metrics` requires `ROLE_ADMIN`. A test running only as an admin user expecting 200 does not prove `USER` is blocked; a filter-bypassing test is worse because even anonymous gets 200. Always include **negative tests**: anonymous rejected, USER gets 403, and ADMIN gets 200.

Spring Security `hasRole("ADMIN")` checks authority `ROLE_ADMIN` by default. `@WithMockUser(roles="ADMIN")` and `@WithMockUser(authorities="ADMIN")` **are not equivalent** regarding prefixes. A 403 caused by a missing role prefix calls for fixing the fixture or policy, not disabling security.

### 4.3. CSRF

In many servlet apps using browser/cookie/session authentication, CSRF protection applies to unsafe methods like POST/PUT/PATCH/DELETE. An authenticated user still gets 403 without a valid token. Never disable all filters just to get GET and POST passing together.

Spring Security Test offers a request postprocessor:

```java
mvc.perform(post("/api/items")
        .with(user("viewer").roles("USER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"draft\"}"))
        .andExpect(status().isCreated());
```

This snippet belongs to the full example, requiring `spring-security-test` and security-enabled MockMvc. Whether CSRF is required depends on the threat model: stateless Bearer token APIs differ from browser cookie/session APIs. Saying “REST APIs never need CSRF” is false across architectures.

### 4.4. Security response headers

Spring Security adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and cache headers by default. When the security filter chain is stripped from MockMvc, tests checking only status/body miss the missing headers. HSTS is added conditionally for HTTPS and should not be asserted unconditionally on plain HTTP; CSP may require explicit configuration.

### 4.5. Custom Servlet Filters

`addFilters=false` is not limited to Spring Security. It can also skip application-defined filters for:

- tenant context / row ownership;
- correlation IDs / MDC / tracing / audit;
- custom request validation or body wrappers;
- rate limiting;
- Servlet-filter-layer CORS;
- custom security headers.

A test skipping a tenant filter may return valid JSON against a default fixture while real services leak data across tenants. In multi-tenant systems, that is a real security flaw, not merely missing test coverage.

## 5. Bypassing filters does not disable security at every layer

Method security is a notable example:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}

@Service
class AccountService {
    @PreAuthorize("hasRole('ADMIN')")
    public void closeAccount() {
        // Protected by method-security advice when enabled.
    }
}
```

This is an **illustrative snippet**, not a file in the runnable app below. When method security is enabled and the service is called through a Spring proxy, `@PreAuthorize` can still deny calls even if Servlet filters were stripped from MockMvc. Spring Boot `starter-security` **does not enable method security automatically** in every app; `@EnableMethodSecurity` is needed.

Likewise, MVC interceptors, Bean Validation, controller advice, and DB policies have distinct boundaries. Avoid both false inferences: “`addFilters=false` disables all security” and “we still got 403 so security filters must be tested”.

## 6. Distinguishing HTTP errors accurately

| Outcome | Possible cause | How to verify |
|---|---|---|
| 401 with HTTP Basic/Bearer | Unauthenticated, missing/wrong credentials | Authentication entry point and principal |
| 403 as user on admin GET | Authorization denial | Role/authority, matcher, method security |
| 403 on user POST | Missing/invalid CSRF or authorization | Retry with `csrf()` token when required by policy |
| 302 to login | Form login entry point | Redirect target/session |
| 400 | DTO/body/Bean Validation | JSON/content type/validators |
| 404 | Missing route/handler or resource-hiding policy | Route mapping, filter paths |
| 405 | Disallowed HTTP method | `@GetMapping`/`@PostMapping` |
| 5xx | Exception/service/config error | Root cause, redacted logs |

When a POST is **both anonymous and missing CSRF**, the CSRF filter can reject before the authentication entry point, yielding 403 instead of 401. To isolate causes, test anonymous GET separately, authenticated POST without CSRF separately, anonymous POST with CSRF separately, and finally authenticated POST with CSRF.

## 7. Java 17+ / Spring Boot 3.5 example: one application, two test paths

The demo application exposes:

- `GET /public/ping` — public.
- `GET /api/items` — requires authenticated user.
- `POST /api/items` — authenticated and valid CSRF token.
- `GET /api/admin/metrics` — `ROLE_ADMIN` only.

Security configuration uses HTTP Basic so 401/403 are easy to observe, with `InMemoryUserDetailsManager` holding **two fake demo-only accounts** and no DB. The first test class keeps filters active (9 methods). The second intentionally strips filters from MockMvc while also sending real HTTP requests to `RANDOM_PORT` (7 methods). **Total: 16 JUnit tests.**

Never use demo credentials in production; production requires an identity provider/user store and HTTPS.

### 7.1. Dependency snippets

**Gradle Groovy DSL** in a project already specifying the Boot 3.5 plugin, BOM/dependency management, repositories, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven** in a project with Spring Boot 3.5 parent/BOM and appropriate compiler/Surefire plugins:

```xml
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
```

These are **dependency excerpts**, not complete build files. `spring-security-test` must be declared explicitly to use `@WithMockUser`, `user(...)`, and `csrf()`.

### 7.2. File tree

```text
src/
├── main/java/com/example/securityfilters/
│   ├── SecurityFiltersApplication.java
│   ├── DemoSecurityConfiguration.java
│   └── ItemController.java
└── test/java/com/example/securityfilters/
    ├── FilterEnabledMockMvcTest.java
    └── BypassMockMvcAndRealHttpTest.java
```

### 7.3. Main application

**File `src/main/java/com/example/securityfilters/SecurityFiltersApplication.java`:**

```java
package com.example.securityfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFiltersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFiltersApplication.class, args);
    }
}
```

### 7.4. Real security configuration

**File `src/main/java/com/example/securityfilters/DemoSecurityConfiguration.java`:**

```java
package com.example.securityfilters;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(viewer, admin);
    }
}
```

**Explanation:** public URLs use `permitAll`, yet the filter chain still runs and adds headers. Admin URLs require `ROLE_ADMIN`. Remaining URLs require an authenticated principal. HTTP Basic returns 401 instead of a form-login 302. CSRF stays enabled for POSTs. Passwords are **demo fakes**, encoded via `PasswordEncoder`; never hardcode them in production apps.

To separate Servlet filters from method security cleanly, the demo application **omits `@EnableMethodSecurity`**. Admin restrictions live solely in the request-level `SecurityFilterChain`.

### 7.5. Deterministic controller

**File `src/main/java/com/example/securityfilters/ItemController.java`:**

```java
package com.example.securityfilters;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    public record Item(String id, String name) {}
    public record NewItem(String name) {}

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/items")
    public List<Item> items() {
        return List.of(new Item("item-1", "Sample"));
    }

    @PostMapping("/api/items")
    @ResponseStatus(HttpStatus.CREATED)
    public Item create(@RequestBody NewItem body) {
        return new Item("created-1", body.name());
    }

    @GetMapping("/api/admin/metrics")
    public Map<String, Integer> metrics() {
        return Map.of("items", 1);
    }
}
```

The controller does not check principals, roles, or CSRF itself; security filters handle that before `DispatcherServlet`. Since the demo has no DB, status 201 indicates only that a response was created, not that a transaction committed.

## 8. Tests keeping the filter chain enabled: 9 recommended cases

**File `src/test/java/com/example/securityfilters/FilterEnabledMockMvcTest.java`:**

```java
package com.example.securityfilters;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = SecurityFiltersApplication.class)
@AutoConfigureMockMvc
class FilterEnabledMockMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void publicRouteIs200AndHasSecurityHeader() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("up"))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void anonymousCannotReadProtectedItems() throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "viewer", roles = "USER")
    void authenticatedUserCanReadItems() throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("item-1"));
    }

    @Test
    void regularUserCannotReadAdminMetrics() throws Exception {
        mvc.perform(get("/api/admin/metrics")
                .with(user("viewer").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminUserCanReadAdminMetrics() throws Exception {
        mvc.perform(get("/api/admin/metrics")
                .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").value(1));
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("viewer").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfWithoutAuthenticationIsUnauthorized()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedPostWithCsrfIsCreated() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("viewer").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("created-1"))
                .andExpect(jsonPath("$.name").value("draft"));
    }

    @Test
    void invalidCsrfIsForbiddenEvenWithUser() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("viewer").roles("USER"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isForbidden());
    }
}
```

**Expected:** 9 JUnit methods pass in a valid Spring Boot 3.5/Spring Security 6.x test environment. Each test checks its own invariant rather than forcing every case to 200:

| Scenario | HTTP status |
|---|---:|
| Public GET without login | 200 and `nosniff` header |
| Anonymous protected GET | 401 |
| Mock `ROLE_USER` protected GET | 200 |
| `ROLE_USER` admin GET | 403 |
| `ROLE_ADMIN` admin GET | 200 |
| `ROLE_USER` POST missing CSRF | 403 |
| Anonymous POST with CSRF | 401 |
| `ROLE_USER` POST with valid CSRF | 201 |
| `ROLE_USER` POST with invalid CSRF | 403 |

`@WithMockUser` verifies URL policies using a mock principal; it **does not** test real password validation. The `user(...)` request postprocessor requires proper Spring Security MockMvc integration. With Boot's default auto-configured MockMvc and matching dependencies, context filters are attached. When building standalone/manual MockMvc, apply `springSecurity()` or wire the chain accordingly.

## 9. Control test: MockMvc bypasses, real HTTP still protects (7 cases)

**File `src/test/java/com/example/securityfilters/BypassMockMvcAndRealHttpTest.java`:**

```java
package com.example.securityfilters;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = SecurityFiltersApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureMockMvc(addFilters = false)
class BypassMockMvcAndRealHttpTest {

    @Autowired MockMvc mvc;
    @LocalServerPort int port;

    private static final HttpClient CLIENT =
            HttpClient.newHttpClient();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private HttpResponse<String> call(HttpRequest request)
            throws Exception {
        return CLIENT.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void mockMvcAnonymousProtectedGetCanReturn200()
            throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("item-1"));
    }

    @Test
    void mockMvcAnonymousAdminGetCanReturn200()
            throws Exception {
        mvc.perform(get("/api/admin/metrics"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").value(1));
    }

    @Test
    void mockMvcAnonymousPostWithoutCsrfCanReturn201()
            throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("draft"));
    }

    @Test
    void mockMvcLacksSecurityHeaderFromSkippedFilter()
            throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        "X-Content-Type-Options"));
    }

    @Test
    void realHttpAnonymousGetIs401() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        assertThat(call(request).statusCode()).isEqualTo(401);
    }

    @Test
    void realHttpAnonymousPostWithoutCsrfIs403()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"draft\"}"))
                .build();

        assertThat(call(request).statusCode()).isEqualTo(403);
    }

    @Test
    void realHttpValidBasicAuthenticationCanRead()
            throws Exception {
        String credentials = Base64.getEncoder()
                .encodeToString(
                        "viewer:viewer-pass".getBytes(
                                StandardCharsets.UTF_8));

        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .timeout(Duration.ofSeconds(5))
                .header("Authorization", "Basic " + credentials)
                .GET()
                .build();

        HttpResponse<String> response = call(request);

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("item-1");
    }
}
```

These are **7 `@Test` methods**. Java 17's `HttpClient.newHttpClient()` is used directly without try-with-resources on `HttpClient`. HTTP requests travel over loopback `127.0.0.1` to the Spring Boot-assigned port, needing no internet or external IdP.

### 9.1. Meaning of the control contrast

| Request | MockMvc `filters=false` | Real server `RANDOM_PORT` |
|---|---:|---:|
| Anonymous GET `/api/items` | 200 | 401 |
| Anonymous GET `/api/admin/metrics` | 200 | 401 in HTTP Basic demo |
| Anonymous POST `/api/items` missing CSRF | 201 | 403 |
| GET `/public/ping` | 200, no `nosniff` from filter | 200, security header per configuration |
| GET `/api/items` with valid Basic | No auth needed on bypass path | 200 after auth |

A single test class both starts an HTTP server and injects `MockMvc`: those two objects **do not share the same filter path when `addFilters=false`**. The flag alters the MockMvc builder without disabling Servlet filters on the real server.

### 9.2. Do not extrapolate @WithMockUser into real authentication

The default MockMvc test keeps filters active and uses a fake `Authentication` to verify URL authorization. The real HTTP test sends an actual HTTP Basic header through the demo's `InMemoryUserDetailsManager` and `PasswordEncoder`. The latter tests more of Basic authentication, yet still **does not** prove OAuth2/JWT/TLS, cookie/session login, or an external production identity provider.

## 10. Running the example and verifying outcomes

**Linux/macOS with Gradle Wrapper:**

```bash
./gradlew test --tests "com.example.securityfilters.FilterEnabledMockMvcTest"
./gradlew test --tests "com.example.securityfilters.BypassMockMvcAndRealHttpTest"
```

**Linux/macOS with Maven Wrapper:**

```bash
./mvnw -Dtest=FilterEnabledMockMvcTest test
./mvnw -Dtest=BypassMockMvcAndRealHttpTest test
```

**Windows PowerShell:**

```powershell
.\gradlew.bat test --tests "com.example.securityfilters.FilterEnabledMockMvcTest"
.\gradlew.bat test --tests "com.example.securityfilters.BypassMockMvcAndRealHttpTest"

# Or use Maven Wrapper when the project is Maven:
.\mvnw.cmd "-Dtest=FilterEnabledMockMvcTest" test
.\mvnw.cmd "-Dtest=BypassMockMvcAndRealHttpTest" test
```

Pick the **single** build tool configured in your project rather than running both Gradle and Maven. Inspect the JUnit report to verify **16 methods executed**, with zero skipped or disabled. For `RANDOM_PORT`, CI must allow binding loopback sockets and ephemeral ports. No DB, real credentials, or Docker is needed.

**Design expectation:** all 16 tests pass in a compatible Spring Boot 3.5/Spring Security 6.x environment. This code was reviewed against the APIs; no runtime compilation/test execution is claimed during authoring of this Knowledge lesson.

## 11. When is disabling filters acceptable?

It can be used deliberately for a **controller-only test** when the primary objective is:

- JSON serialization/deserialization or HTTP DTO contracts;
- request mapping, `@RequestBody`, and response statuses;
- Bean Validation at the MVC layer;
- `@ControllerAdvice` exception body mapping;
- controller -> mocked business service interactions.

Even then, you must ensure:

1. Security is **not an acceptance criterion** for that test.
2. Class/test names clearly state MVC/controller-only scope.
3. No Servlet filter is required by the controller for business results.
4. A **separate security-enabled suite** protects all critical URLs.
5. `addFilters=false` is never placed on a base test class causing all web tests to drop filters silently.
6. Production `SecurityFilterChain` is never modified just to make tests pass.
7. Negative tests exist for anonymous/USER/ADMIN/CSRF.
8. CI runs every test group and never treats skipped security suites as PASS.

When testing pure business logic, test the service directly without MockMvc. When testing HTTP security contracts, keep filters enabled and supply valid user/CSRF fixtures.

## 12. @WebMvcTest, manually built MockMvc, and custom SecurityFilterChain

`@WebMvcTest(MyController.class)` loads only the MVC slice. Spring Security may be auto-configured in the slice, yet the app's custom `@Configuration` is not guaranteed to be scanned like full context. Therefore, when testing security policies:

- Use `@Import(MySecurityConfiguration.class)` when the slice must load the real config.
- Use `@MockitoBean` (Spring Framework 6.2 / Boot 3.4+) for business collaborators outside the MVC slice.
- Never rely on the slice's default security to conclude production custom matchers work.
- If policy parity is hard to guarantee, use `@SpringBootTest + @AutoConfigureMockMvc` with filters enabled.

`MockMvcBuilders.standaloneSetup(controller)` fits controller-only tests without attaching Spring Security's filter chain. When building MockMvc manually from `WebApplicationContext`:

```java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

This is a snippet requiring `WebApplicationContext`/imports and `spring-security-test`. When using Boot's auto-configured MockMvc properly, manually constructing the builder is rarely needed.

## 13. @WithMockUser and user() do not disable authorization

- `@WithMockUser(username="alice", roles="USER")` builds a mock authenticated principal. URL access rules still run.
- `user("alice").roles("USER")` applies an identity per MockMvc request.
- `roles="ADMIN"` creates `ROLE_ADMIN`, unlike `authorities="ADMIN"` without a custom prefix.
- `@WithUserDetails` helps when the app uses a custom `UserDetailsService`/principal.
- `@WithSecurityContext` supports custom authentication objects.
- The `jwt()` postprocessor for OAuth2 resource-server authorization scenarios can simulate JWT authentication, yet **does not prove JWT signatures are verified by a real decoder**.

For production OAuth/JWT, write real decoder/token/issuer/audience tests when those are in scope. For browser cookie/session auth, test sessions, login/logout, CSRF, and cookie flags per contract.

## 14. Other defense layers requiring dedicated tests

### 14.1. Method security

If method-security advisors are enabled via `@EnableMethodSecurity`, `@PreAuthorize` can still reject service calls even when MockMvc filters were disabled. That **never** substitutes for URL authorization tests. Method security also depends on proxies, avoiding self-invocation, and proper authentication context.

### 14.2. CORS

CORS may be handled in `SecurityFilterChain`, a Servlet CORS filter, or Spring MVC handler mappings. `addFilters=false` can skip filter-layer CORS while leaving MVC CORS intact. Test CORS using `OPTIONS` preflight, `Origin`, `Access-Control-Request-Method`, and expected `Access-Control-Allow-*` headers per real config; never infer it from a 200 GET.

### 14.3. Tenant/audit/tracing filters

Skipping a tenant filter can leave a default or null tenant, causing tests to read the wrong data or miss isolation checks. Skipping audit/correlation filters can drop request IDs, MDC, and security principals from logs. Multi-tenant systems need tests verifying both blocked tenant mismatches and DB-layer owner readbacks.

### 14.4. Security response headers

Filter-enabled MockMvc tests should assert required headers such as `X-Content-Type-Options: nosniff`. Do not assert HSTS unconditionally over plain HTTP, and do not assume CSP is always active. TLS/mTLS/HTTPS require testing at layers with real transport security.

## 15. Diagnose 401/403 instead of bypassing filters

Order of steps:

1. Confirm method, path, content type, and body.
2. Distinguish 401 authentication, 302 login redirect, and 403 authorization/CSRF.
3. For POST/PUT/PATCH/DELETE, check the CSRF token when required by policy.
4. Check whether `@WithMockUser`/`user(...)` carries the right roles/authorities.
5. Check whether the principal is genuinely picked up by Spring Security MockMvc integration.
6. Check which `SecurityFilterChain` matches the URL and the ordering across multiple chains.
7. In `@WebMvcTest`, check whether the custom security configuration was imported.
8. Inspect custom authentication converters, JWT claims, OAuth scopes, or role hierarchies if present.
9. Inspect method security/proxies, custom filters, and tenant resolvers.
10. Read the root cause, resolved exception, and headers in redacted logs.
11. Fix test fixtures when test inputs are incomplete; alter production policy **only when production policy is genuinely wrong**.
12. Add negative regression tests and run the full security suite.

You may use `andDo(print())` while debugging locally, yet never dump passwords, tokens, PII, or real `Authorization` headers into CI artifacts.

### 15.1. A 403 test response may be the right behavior

If role `USER` is denied on an admin endpoint, 403 is the expected outcome. Disabling filters to force 200 changes the **test question**. Name the test `userCannotReadAdmin()`, assert 403, and pair it with `adminCanReadAdmin()` asserting 200.

## 16. Common anti-patterns

| Anti-pattern | Problem | Better approach |
|---|---|---|
| `addFilters=false` on every test | Loses security/custom filter coverage | Narrow opt-out; default filter-enabled |
| Using only an admin test user | Fails to test least privilege | Anonymous/USER/ADMIN matrix |
| Disabling production CSRF because POST test returned 403 | Changes threat model to dodge test setup | `csrf()` or threat-reviewed policy |
| `@WebMvcTest` omitting custom security config | Slice test diverges from production | `@Import` or full-context test |
| All positive endpoints return 200 | Fails to prove denied paths | 401/403/invalid-CSRF tests |
| Mocking JWT and claiming signature validated | Decoder/auth pipeline was mocked | Real token/decoder integration |
| Disabling tenant filter so controller JSON passes | Fails to test tenant isolation | Filter-enabled tenant tests |
| Using standalone MockMvc and calling it E2E security | No real filter chain | `springSecurity()` or Boot MockMvc |
| Running only MockMvc and calling it a socket test | Skips real servlet container | `RANDOM_PORT` + real `HttpClient` |
| Ignoring security headers | Misses defense-in-depth | Header assertions |
| Fixing tests with `anyRequest().permitAll()` | Stops testing production rules | Keep actual `SecurityFilterChain` |
| Dropping security tests from CI | Loses regression guard | Run enabled suite and track skips |

## 17. Practice exercises with answers

**A — POST 403 despite `@WithMockUser`:** Check CSRF. If CSRF policy is enabled, add `csrf()` and add negative missing/invalid token tests; do not disable filters.

**B — USER into admin returns 403:** Right behavior when URL requires `ROLE_ADMIN`. Assert 403 for USER and 200 for ADMIN instead of bypassing.

**C — MockMvc GET 200 yet real HTTP 401:** `addFilters=false` changes only MockMvc; the server still executes `SecurityFilterChain`.

**D — Does `@WithMockUser` verify passwords?** No. It mocks the authentication object; use real HTTP Basic/JWT verification tests when needed.

**E — `addFilters=false` yet `@PreAuthorize` still denies?** Yes, because method-security AOP acts at a different boundary when enabled.

**F — Is a CORS test passing with filters off sufficient?** No. CORS may run at the Servlet filter, Spring Security, or MVC layer; test preflight/headers against the real policy.

**G — Is testing only admin GET 200 sufficient?** No. A broken `permitAll` config also returns 200; negative tests are mandatory.

**H — When is `addFilters=false` acceptable?** When specifically testing MVC/DTO/validation contracts, custom filters are irrelevant to that behavior, and a complete security-enabled suite exists alongside it.

**I — Is enabling CSRF mandatory for every API?** It depends on browser credentials, sessions/cookies, and the threat model; never decide from the label REST API or a failing test.

**J — Does a passing mock JWT test prove token signatures?** No. You need real `JwtDecoder` tests with valid and invalid token signatures for the authentication stack.

## 18. QA checklist

- [ ] Clearly documented whether a test checks business logic, MVC contracts, or security contracts.
- [ ] Avoided using `addFilters=false` to hide undiagnosed 401/403 failures.
- [ ] Security-enabled tests retain the default `addFilters=true`.
- [ ] Anonymous protected requests have negative tests.
- [ ] USER cannot enter admin routes; ADMIN can.
- [ ] Unsafe requests have valid, missing, and invalid CSRF tests when applicable.
- [ ] Distinguished fake users from real authentication/JWT validation.
- [ ] Security response headers are asserted on filter-enabled paths.
- [ ] `@WebMvcTest` imports the right security config when testing policies.
- [ ] Custom tenant/CORS/audit filters have dedicated tests.
- [ ] Method security is understood as an independent layer.
- [ ] Never altered production CSRF/auth config just to make tests green.
- [ ] No real credentials/secrets/PII appear in tests.
- [ ] Real HTTP smoke tests exist when Servlet container behavior matters.
- [ ] HTTP statuses match the exact Basic/form/Bearer scheme rather than guessing.
- [ ] Test classes run independently without order dependence.
- [ ] CI accurately reports executed/failed/skipped tests.
- [ ] Java 17, Spring Boot 3.5, and `security-test` imports are compatible.
- [ ] Any bypass test explicitly states controller-only scope.
- [ ] 2xx status in bypass mode is never treated as proof of security.

## 19. Conclusion

**When you disable filters to make a test pass, you usually changed the question the test asks.** Instead of asking “is this request properly protected?”, you are asking “what does the controller do when Servlet filters are skipped?”. Those two outcomes are not interchangeable.

With Spring Boot 3.5/Spring Security 6:

- `@AutoConfigureMockMvc(addFilters=false)` removes context filters from **`MockMvc`**, without disabling security on a real HTTP server.
- It can mask authentication, authorization, CSRF, and custom-filter bugs.
- `@WithMockUser`, `user(...)`, and `csrf()` let you build valid requests **while keeping the security policy active**.
- Method security, MVC validation, and database policies operate at separate boundaries.
- Filter bypasses belong strictly to intentional controller-only tests backed by a security integration suite covering the gap.
- Security tests must check both **allowed** and **denied** paths.

The sample shares one production controller and security config across 16 JUnit methods, clearly demonstrating MockMvc bypasses returning 200/201 while the real server returns 401/403. Keep this boundary in mind before fixing any failing test by deleting filters.

## Official references

- [Spring Boot 3.5 — AutoConfigureMockMvc API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): `addFilters` defaults to true.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvc, WebMvcTest, SpringBootTest, RANDOM_PORT.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): importing security config in MVC slices.
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `FilterChainProxy` and `springSecurity()` configurer.
- [Spring Security — Running a Test as a User](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `@WithMockUser` and `user(...)`.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `asHeader()`, invalid tokens.
- [Spring Security — CSRF threat model](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF for browser/unsafe methods.
- [Spring Security — HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matchers/roles.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
- [Spring Security — Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): `nosniff`, frame, HSTS.
