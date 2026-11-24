# MockMvc Unexpectedly Returning 401, 403, or 404

## 1. Goal and Scope

In **Spring Boot - testing**, under **Test Troubleshooting**, a MockMvc test expecting HTTP 200 or 201 yet receiving **401 Unauthorized**, **403 Forbidden**, or **404 Not Found** does not pinpoint the root cause on its own. The request might be rejected by the Spring Security filter chain before reaching the controller; a `POST` might fail **CSRF** validation; the user may lack a **`GrantedAuthority`**; the path may miss MVC handler mappings; or the controller ran and the business entity simply does not exist.

This lesson uses **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, Spring Security 6.4, JUnit Jupiter, and `spring-security-test`**. The complete example builds an explicit `SecurityFilterChain`, `DemoController` with public/private/admin/item endpoints, a service returning `Optional<ItemView>`, a **`@WebMvcTest` + `@MockitoBean` + `@Import(SecurityConfig.class)`** suite, and a **`@SpringBootTest` + `@AutoConfigureMockMvc`** suite. Every status includes positive and negative controls: anonymous 401, missing-role/CSRF 403, routing 404 vs domain 404, and valid 200 responses.

**Never "fix" tests by disabling all filters, granting `ROLE_ADMIN` everywhere, changing expected statuses to pass, or mocking the controller under test.** Identify which security, MVC, or business layer produced the status before touching code.

All outcomes described here are **expected behaviors derived from assertions**, not captured Gradle logs run during authoring.

## 2. Pipeline of a MockMvc Request

~~~text
MockMvc.perform(MockHttpServletRequest)
            |
            v
Servlet filters registered with MockMvc
            |
            +-- Spring Security FilterChainProxy
            |       |
            |       +-- securityMatcher picks SecurityFilterChain
            |       +-- Authentication / SecurityContext
            |       +-- CsrfFilter on unsafe methods
            |       +-- AuthorizationFilter
            |       +-- EntryPoint / AccessDeniedHandler
            |
            v  if filters allow request through
DispatcherServlet
            |
            +-- HandlerMapping
            +-- HandlerAdapter + binding/converter/validation
            +-- Controller / RestController
            +-- Service / @ControllerAdvice
            |
            v
MockHttpServletResponse
~~~

This is a conceptual diagram; exact filter ordering depends on your `SecurityFilterChain`. Crucially, **filters can return 401 or 403 before `DispatcherServlet` ever looks up a handler**. Consequently, an anonymous request to a nonexistent URL can receive 401 instead of 404, and an authenticated user lacking a role receives 403 before the controller executes. Only after security lets the request pass can you reliably diagnose MVC mappings.

| Status | Common Sources | First Diagnostic Step |
| --- | --- | --- |
| 401 | Anonymous call to protected URL, HTTP Basic/Bearer challenge | `AuthenticationEntryPoint`, principal, `WWW-Authenticate` |
| 401 | Invalid credentials or JWT | Authentication provider/decoder trace |
| 403 | Logged-in user missing `ROLE_`/authority | Authorities, `hasRole`/`hasAuthority`, `@PreAuthorize` |
| 403 | `POST`/`PUT`/`PATCH`/`DELETE` missing CSRF | `CsrfFilter`, `csrf()` |
| 404 | URI/method/path mismatch | `HandlerMapping`, request URI |
| 404 | Controller ran yet business entity missing | Handler is controller, service result |
| 404 | Static resource fallback | `ResourceHttpRequestHandler`, `NoResourceFoundException` |
| 404 | Custom security hiding resource existence | `AccessDeniedHandler` or controller policy |

**Status codes are symptoms, not stack traces.** Diagnose using the selected handler, resolved exception, registered filters, and a positive control.

## 3. 401 Unauthorized: Authentication and Entry Points

When an anonymous request hits an endpoint requiring authentication, Spring Security delegates to an **`AuthenticationEntryPoint`**. With **`httpBasic(Customizer.withDefaults())`**, the response is typically **401** with **`WWW-Authenticate: Basic`**. With **`formLogin`**, anonymous requests often receive a **302 redirect** to the login page instead of 401. With OAuth2 Resource Server / Bearer tokens, token failures yield 401 with a Bearer header depending on configuration.

**Causes of unexpected 401s:**
- Test omits **`@WithMockUser`** or **`with(user("alice"))`**.
- Test uses `MockMvcBuilders.standaloneSetup` without integrating Spring Security.
- `@WebMvcTest` omits production `SecurityConfig`, falling back to Boot's default chain securing every URL.
- Authentication fixture supplies a username without real credential verification when tested against a real auth filter.
- Another `SecurityFilterChain` matched first due to `@Order`/`securityMatcher`.
- A custom stateless/token filter ignores mock `Authentication` the way the test expects.
- Missing or malformed `Authorization` header; HTTP Basic not enabled.
- Wrong route was blocked by security before MVC could return 404.

**`@WithMockUser`** populates a mock `Authentication` in Spring Security's test context; the user **does not need to exist in a database**. It is great for testing authorization and handlers, yet **does not verify password hashing, JWT signatures**, issuer/audience, authentication managers, or login forms.

Expected positive test:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void authenticatedCanReadProfile() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

Opposite anonymous test:

~~~java
@Test
void anonymousNeedsAuthentication() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isUnauthorized());
}
~~~

These snippets come from the complete test project in section 7.

## 4. 403 Forbidden: Authorization vs CSRF

**403 Authorization:** user holds `ROLE_USER` while the endpoint requires **`hasRole("ADMIN")`**, i.e., `ROLE_ADMIN`. **403 CSRF:** a `POST` to a **`permitAll`** route is still rejected by `CsrfFilter` if the token is missing. Test these two causes separately.

~~~text
GET /api/admin/report
user = alice; authorities = [ROLE_USER]
rule = hasRole("ADMIN")
=> 403

POST /api/public/echo
url authorization = permitAll
csrf enabled, no token
=> 403
~~~

### Roles and Authorities

- **`hasRole("ADMIN")`** requires GrantedAuthority **`ROLE_ADMIN`**.
- **`@WithMockUser(roles = "ADMIN")`** grants `ROLE_ADMIN`.
- **`@WithMockUser(authorities = "ROLE_ADMIN")`** grants that exact string as well.
- **`hasAuthority("SCOPE_reports.read")`** differs from `hasRole(...)`; OAuth scopes use distinct authority names.
- Never pass **`roles = "ROLE_ADMIN"`** when you mean the `ADMIN` role; Spring Security's `roles` shortcut prepends `ROLE_` automatically.

### `permitAll` Does Not Disable CSRF

By default, Spring Security protects unsafe HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) with CSRF unless configured otherwise. `GET`, `HEAD`, `OPTIONS`, and `TRACE` are normally exempt under the default matcher.

~~~java
mvc.perform(post("/api/public/echo")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"message\":\"ok\"}"))
    .andExpect(status().isOk());
~~~

Security test support also offers **`csrf().asHeader()`** and **`csrf().useInvalidToken()`**. If adding a valid CSRF token to a failing 403 `POST` still returns 403, investigate URL authorization, method security, roles, and filter chain matching rather than piling on extra roles.

**CSRF policy must be an application decision.** Truly stateless APIs using no cookie/session credentials may adopt a different policy, yet never disable CSRF in tests merely to hide an active CSRF requirement in production. Browser auto-attached credentials carry a different threat model than manually attached bearer tokens.

## 5. 404: Missing MVC Route vs Missing Business Object

**Routing 404:** Controller declares **`GET /api/items/{id}`**, while the test requests **`GET /api/item/42`**; no controller mapping matches that URI.

**Domain 404:** `GET /api/items/99` matches `DemoController.item`, `InventoryService.find(99)` returns `Optional.empty`, and the controller returns `ResponseEntity.notFound().build()`. Same 404 status, yet the controller handler actually executed.

**Resource 404:** In Spring MVC, static resource handling can pick up unmatched URLs and throw **`NoResourceFoundException`**. Debugging reveals **`ResourceHttpRequestHandler`** instead of a `null` handler; do not mistake that for an API controller handling the request.

**Custom 404:** A system may intentionally mask unauthorized resources with 404; that reflects authorization policy rather than a guaranteed bad path.

How to separate them:
1. Send the request as an authenticated user authorized to clear security filters.
2. Inspect **`MvcResult.getHandler()`** or **`handler().handlerType(DemoController.class)`**.
3. Inspect **`getResolvedException()`**; when a controller returns `ResponseEntity.notFound()`, the exception can be `null`.
4. Stub/verify the service mock and check the item ID.
5. Check route prefixes, HTTP methods, `contextPath`, `servletPath`, and trailing slashes.
6. Verify the controller was component-scanned or listed in `@WebMvcTest`.

**Never send an anonymous `GET` to a wrong URL and assume MVC returned 404**: security filters often intercept first with 401.

## 6. Java 17 / Spring Boot 3.4.5 Project

### 6.1. File Tree

~~~text
settings.gradle
build.gradle
src/main/java/com/example/mockdiag/MockDiagApplication.java
src/main/java/com/example/mockdiag/SecurityConfig.java
src/main/java/com/example/mockdiag/ItemView.java
src/main/java/com/example/mockdiag/InventoryService.java
src/main/java/com/example/mockdiag/DemoController.java
src/test/java/com/example/mockdiag/DemoControllerSecuritySliceTest.java
src/test/java/com/example/mockdiag/FullSecurityContractTest.java
~~~

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'mockmvc-security-diagnostics'
~~~

### 6.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
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
~~~

**`spring-security-test`** provides `@WithMockUser`, `SecurityMockMvcRequestPostProcessors.csrf()`, `user()`, `httpBasic()`, `authentication()`, and JWT test helpers for OAuth2 testing. **`spring-boot-starter-test`** brings MockMvc, Spring TestContext, JUnit Jupiter, Mockito, and AssertJ. No DB, Kafka, Docker, or real embedded server is needed for MockMvc.

### 6.4. `MockDiagApplication.java`

~~~java
package com.example.mockdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockDiagApplication.class, args);
    }
}
~~~

Application and components share the root package so full `@SpringBootTest` scans controllers, security, and services.

### 6.5. `SecurityConfig.java`

~~~java
package com.example.mockdiag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // CSRF remains enabled by default.
        return http.build();
    }
}
~~~

Rules are ordered: public and admin before **`anyRequest`**. **`httpBasic`** configures an `AuthenticationEntryPoint` so anonymous `GET /api/me` returns 401. **`hasRole("ADMIN")`** demands `ROLE_ADMIN`. **CSRF stays enabled**, so even public `POST` requests require a token under the default CSRF matcher.

If production uses form login or Bearer JWTs, expected auth responses differ; test your real config rather than assuming HTTP Basic challenges everywhere.

### 6.6. `ItemView.java`

~~~java
package com.example.mockdiag;

public record ItemView(long id, String name) {
}
~~~

Spring MVC/Jackson serializes this record to JSON with `id` and `name` fields.

### 6.7. `InventoryService.java`

~~~java
package com.example.mockdiag;

import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    public Optional<ItemView> find(long id) {
        return id == 42L
            ? Optional.of(new ItemView(42L, "keyboard"))
            : Optional.empty();
    }
}
~~~

Full-context tests use the real service; WebMvc slices mock this dependency.

### 6.8. `DemoController.java`

~~~java
package com.example.mockdiag;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final InventoryService inventory;

    public DemoController(InventoryService inventory) {
        this.inventory = inventory;
    }

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping(
        value = "/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping(
        value = "/admin/report",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String adminReport() {
        return "restricted";
    }

    @GetMapping("/items/{id}")
    public ResponseEntity<ItemView> item(
            @PathVariable long id) {
        return inventory.find(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
        value = "/public/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public EchoResponse echo(
            @RequestBody EchoRequest request) {
        return new EchoResponse(request.message());
    }

    public record EchoRequest(String message) {
    }

    public record EchoResponse(String message) {
    }
}
~~~

The controller exposes **public GET**, **private GET**, **admin GET**, **item GET**, and **public POST** endpoints. No custom `@ControllerAdvice` or `@PreAuthorize` is included so every status maps directly to a clear cause.

### 6.9. API Outcome Matrix

| Request | Auth/CSRF | Expected Result |
| --- | --- | --- |
| `GET /api/public/ping` | Anonymous | 200 `pong` |
| `GET /api/me` | Anonymous | 401 |
| `GET /api/me` | user `alice` | 200 `alice` |
| `GET /api/admin/report` | `ROLE_USER` | 403 |
| `GET /api/admin/report` | `ROLE_ADMIN` | 200 `restricted` |
| `POST /api/public/echo` | Anonymous, no CSRF | 403 |
| `POST /api/public/echo` | Anonymous, valid CSRF | 200 JSON |
| `POST /api/public/echo` | Anonymous, invalid CSRF | 403 |
| `GET /api/items/42` | Authenticated | 200 JSON item |
| `GET /api/items/99` | Authenticated | 404 domain |
| `GET /api/item/42` | Authenticated | 404 route |

## 7. MVC Slice Tests with Real Spring Security Active

**src/test/java/com/example/mockdiag/DemoControllerSecuritySliceTest.java**

~~~java
package com.example.mockdiag;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DemoController.class)
@Import(SecurityConfig.class)
class DemoControllerSecuritySliceTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private InventoryService inventory;

    @Test
    void anonymousPublicIs200() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousProtectedIs401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void authenticatedProtectedIs200() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserDeniedAdmin403() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminAuthorized200() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk())
            .andExpect(content().string("restricted"));
    }

    @Test
    void publicPostWithoutCsrfIs403() throws Exception {
        mvc.perform(post("/api/public/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicPostWithCsrfIs200() throws Exception {
        mvc.perform(post("/api/public/echo")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"));
    }

    @Test
    void publicPostInvalidCsrfIs403() throws Exception {
        mvc.perform(post("/api/public/echo")
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postProcessorCreatesAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    @WithMockUser
    void foundItemUsesControllerAndReturns200()
            throws Exception {
        when(inventory.find(42L))
            .thenReturn(Optional.of(
                new ItemView(42L, "keyboard")));

        mvc.perform(get("/api/items/42"))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(
                DemoController.class))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("keyboard"));

        verify(inventory).find(42L);
    }

    @Test
    @WithMockUser
    void missingItemIsDomain404() throws Exception {
        when(inventory.find(99L))
            .thenReturn(Optional.empty());

        mvc.perform(get("/api/items/99"))
            .andExpect(status().isNotFound())
            .andExpect(handler().handlerType(
                DemoController.class));

        verify(inventory).find(99L);
    }

    @Test
    @WithMockUser
    void wrongSingularPathIsRouting404()
            throws Exception {
        mvc.perform(get("/api/item/42"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser
    void debugMvcResultShowsMatchedDomainHandler()
            throws Exception {
        when(inventory.find(99L))
            .thenReturn(Optional.empty());

        MvcResult result = mvc.perform(get("/api/items/99"))
            .andDo(print())
            .andExpect(status().isNotFound())
            .andReturn();

        assertEquals(404, result.getResponse().getStatus());
        assertNotNull(result.getHandler());
    }
}
~~~

### Explaining the Test Suite

- **`@WebMvcTest(DemoController.class)`** creates an MVC slice with no open socket.
- **`@Import(SecurityConfig.class)`** ensures the slice applies production authorization rules instead of Boot's default lock-all chain.
- **`@MockitoBean InventoryService`** supplies the collaborator because the slice excludes `@Service` beans.
- Anonymous 401, insufficient-role 403, and missing-CSRF 403 are **expected negative contracts**, not broken filters to disable.
- Positive user/admin/CSRF tests confirm endpoints succeed when requirements are met.
- **`missingItemIsDomain404`** asserts the controller handler ran and verifies `service.find`.
- **`wrongSingularPathIsRouting404`** tests a bad URI while authenticated.
- **`MvcResult`** exposes handler and status to tell domain 404 apart from routing 404.

**Never `@MockitoBean` away `AuthenticationFilter` and claim security config was tested.** Mocking `InventoryService` isolates the business boundary while keeping the real `SecurityFilterChain` active in MockMvc.

## 8. Verifying Production Wiring via Full Context

**src/test/java/com/example/mockdiag/FullSecurityContractTest.java**

~~~java
package com.example.mockdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FullSecurityContractTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousPublicStill200() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousProtectedStill401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void realServiceReturnsExistingItem() throws Exception {
        mvc.perform(get("/api/items/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("keyboard"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void realSecurityStillBlocksNonAdmin()
            throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }
}
~~~

**`@SpringBootTest`** loads the full Spring context with the real `InventoryService` and `SecurityConfig`. **`@AutoConfigureMockMvc`** wires MockMvc with application filters. It does not launch a `RANDOM_PORT` HTTP server; `@SpringBootTest` uses a `MOCK` web environment by default. Full-context tests catch mismatches between slice security imports and production component scanning or profiles.

## 9. Reading Diagnostics Properly

Temporarily add **`andDo(print())`** to inspect request, selected handler, resolved exception, and response:

~~~java
mvc.perform(get("/api/items/99")
        .with(user("debug")))
    .andDo(print())
    .andExpect(status().isNotFound());
~~~

Or inspect **`MvcResult`** directly:

~~~java
MvcResult result = mvc.perform(
        get("/api/item/42")
            .with(user("debug")))
    .andReturn();

int actualStatus = result.getResponse().getStatus();
Object handler = result.getHandler();
Exception resolved = result.getResolvedException();
String responseBody =
    result.getResponse().getContentAsString();
~~~

These snippets belong inside test methods, not standalone files. When a security filter rejects a request, **`handler` can be `null`** because `DispatcherServlet` never ran. When static resource fallback handles the URI, `handler` may be **`ResourceHttpRequestHandler`** and the exception **`NoResourceFoundException`**. When a controller returns `ResponseEntity.notFound()`, **`getResolvedException()` is `null`** despite status 404. Always inspect **handler + response + cause**, not just the exception field.

### Selective Logging

Example **`src/test/resources/application-test.yml`** when `@ActiveProfiles("test")` is enabled:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: TRACE
    org.springframework.web.servlet.DispatcherServlet: DEBUG
~~~

This config is illustrative and optional. Spring Security `DEBUG` reveals filter chain/matcher decisions. MVC mapping `TRACE` lists registered request handlers. **Never print Authorization tokens, raw Basic passwords, session cookies, or customer details into public CI logs.** Do not keep `TRACE` enabled permanently in production just for unit test debugging.

## 10. `addFilters=false` and Standalone MockMvc

Spring Boot supports:

~~~java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = false)
class ControllerOnlyExample {
    // Illustrative only; not part of the main project.
}
~~~

**`@AutoConfigureMockMvc(addFilters=false)`** skips registering servlet `Filter` beans in MockMvc. Tests stop returning 401/403 because **security filtering was bypassed**, along with CORS, tracing, tenant, encoding, and custom filters. **Never treat such a test as proof that production authentication, authorization, or CSRF works**. Use it only to isolate pure controller logic when covered by a separate security-enabled suite.

Manual standalone setup:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new DemoController(fakeInventory))
    .build();
~~~

This snippet also assumes `fakeInventory` exists, outside the project files. **`standaloneSetup` does not attach Spring Security's `FilterChainProxy` by default.** For manual `WebApplicationContext` MockMvc setups, apply `SecurityMockMvcConfigurers.springSecurity()` and proper filter/listener wiring. An anonymous 200 in standalone MockMvc never proves a production endpoint is public.

## 11. How Can a `@WebMvcTest` Slice Differ from Production?

**Case A:** Production leaves `/api/public/ping` public, yet `@WebMvcTest` returns 401. Most likely **custom `SecurityConfig` was not imported**, so Boot created its default chain securing all URIs. **Fix:** `@Import(SecurityConfig.class)` plus a full-context security contract test.

**Case B:** `@WebMvcTest` fails context startup with `UnsatisfiedDependencyException`. Controller injects `@Service` missing from the slice. **Fix:** `@MockitoBean` of the right type or `@Import` the fixture. This is not a MockMvc HTTP error because `@Test` never ran.

**Case C:** Test reaches the controller yet gets 404 item missing. The Mockito service mock was unstubbed and returned `Optional.empty()` by default or explicit stub. **Fix:** `when(inventory.find(id)).thenReturn(Optional.of(...))`, assert handler, and verify the call.

**Case D:** Full context registers custom `Filter` beans, interceptors, or `@ControllerAdvice` that differ or are absent in the slice. Compare both levels rather than assuming `@WebMvcTest` includes every production bean.

**Case E:** Test profiles or feature flags differ. `@Profile`/`@ConditionalOnProperty` beans can reshape `SecurityFilterChain` or controllers. Check active test properties explicitly rather than assuming production defaults.

## 12. Roles, Authorities, and Method Security

**`hasRole("ADMIN")`** typically checks for **`ROLE_ADMIN`**. **`@WithMockUser(roles="ADMIN")`** supplies `ROLE_ADMIN`. When security checks **`hasAuthority("SCOPE_reports.read")`**, the fixture must supply that exact authority string, not `roles="reports.read"`.

**`@PreAuthorize`** or `@PostAuthorize` can deny access **after URL-level filters already allowed the request**. With `@EnableMethodSecurity` active and proxied service methods, a controller route can still return 403. When a service is replaced by `@MockitoBean`, method security on the real service does not execute as in production; add a full-context method-security test if that contract matters.

### Multiple `SecurityFilterChain`s

Spring Security supports multiple chains. **`securityMatcher`** picks which chain handles the request, while **`requestMatchers`** applies authorization rules inside that chain. `@Order` and chain specificity matter. Illustrative snippet outside the main project:

~~~java
@Bean
@Order(1)
SecurityFilterChain managementChain(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/actuator/**")
        .authorizeHttpRequests(auth ->
            auth.anyRequest().hasRole("OPS"))
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Real implementation requires `@Order`, `@Bean`, and Actuator/other chain configs. If `/actuator/health` unexpectedly returns 401, editing the public API matcher does **nothing** when the request matched the management chain.

## 13. Real HTTP Basic and JWTs Differ from Mock Users

**`@WithMockUser`** never invokes `UserDetailsService`, `PasswordEncoder`, or a JWT decoder. To test real HTTP Basic credentials, configure a `UserDetailsService`/`PasswordEncoder` fixture and send:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("reader", "secret")))
    .andExpect(status().isOk());
~~~

This snippet **cannot run standalone in the main project** because no `reader`/`secret` user is defined; configure an authentication provider with that user first. Bad passwords must return 401; never equate `@WithMockUser` with password integration testing.

For OAuth2 Resource Server, **`with(jwt())`** injects a test JWT `Authentication` suited for testing authorization, yet skips signature verification, issuer, audience, expiration, and JWK retrieval. Testing the actual decoder requires a matching decoder/token fixture. Sending a raw `Bearer` string header without resource-server configuration will not authenticate automatically.

## 14. CSRF Across Protection Layers

A helpful matrix for a public `POST` endpoint:

| Scenario | Authorization | CSRF | Expected |
| --- | --- | --- | --- |
| Anonymous + no token | `permitAll` | Missing | 403 |
| Anonymous + invalid token | `permitAll` | Invalid | 403 |
| Anonymous + valid token | `permitAll` | Valid | 200 |
| `ROLE_ADMIN` + no token | `permitAll` | Missing | 403 |
| `ROLE_USER` + valid token | `permitAll` | Valid | 200 |
| Public `GET` + no token | `permitAll` | Not required by default | 200 |

CSRF rejects requests before MVC inspects `Content-Type` or JSON. Therefore, a `POST` with no token and malformed JSON returns **403**, then switches to **400** (bad JSON) or **415** (bad media type) once a valid token is added. That shift simply shows the request progressed to the next layer.

## 15. Context Path, Servlet Path, HTTP Method, and Media Types

If an app sets:

~~~properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/gateway
~~~

external URLs carry `/shop/gateway` ahead of the controller path. In MockMvc, request URI, `contextPath`, and `servletPath` must align. Example when only context path is set with matching setup:

~~~java
mvc.perform(get("/shop/api/items/42")
        .contextPath("/shop")
        .with(user("reader")))
    .andExpect(status().isOk());
~~~

This snippet needs matching config and inventory fixtures; when `DispatcherServlet` uses a custom path, set `servletPath` as well. Never hardcode those prefixes into `@RequestMapping` just to appease a test when production controller mappings are right.

**Spring Framework 6.x** path matching does not auto-match trailing slashes as older versions/configs did: `/api/items/42` and `/api/items/42/` can differ. Verify path casing, encoding, URI segments, and servlet mappings in `HandlerMapping`. A wrong HTTP method on a valid path returns **405** instead of 404; incompatible `Accept` vs `produces` returns **406**; wrong `Content-Type` vs `consumes` returns **415**; JSON parse/binding/validation errors return **400**. Do not blame every non-2xx response on Spring Security.

## 16. Controller Advice and Exception Handling

A controller can return `ResponseEntity.notFound()`, throw `ResponseStatusException(HttpStatus.NOT_FOUND)`, or throw a custom domain exception mapped to 404 by `@RestControllerAdvice`. In all three cases, the handler matched. **`MvcResult.getResolvedException()`** surfaces exceptions handled by MVC resolvers, yet stays `null` for `ResponseEntity.notFound()`.

In `@WebMvcTest`, `@ControllerAdvice` normally joins the MVC slice, though package/filter/import rules can cause differences from full context. Exceptions thrown inside security filters before `DispatcherServlet` bypass `@ControllerAdvice`. Verify the exact layer and resolver before editing code.

## 17. CI and SecurityContext Flakiness

A MockMvc test passing alone yet failing in the suite can stem from:
- Manually setting static/mutable `Authentication` or `SecurityContextHolder` without clearing it.
- Class-level `@WithMockUser` leaking onto tests intended to be anonymous.
- HTTP sessions or cookies unexpectedly reused.
- Mockito stubbing/resets, `@MockitoBean` scope, or test order dependence.
- Mutable singleton state in the Spring TestContext cache or misused `@DirtiesContext`.
- Shared custom rate-limiter/filter/tenant state.
- Different active profiles or properties between test classes.
- Parallel JUnit tests sharing credentials, DB state, secrets, or resource IDs.
- CSRF tokens/sessions bound to a different request.
- Expired JWTs or system clock skew on CI.
- Gradle `Test` task `FROM-CACHE` or `UP-TO-DATE` skipping re-execution in the current run.

Let Spring Security Test listeners populate and clear `SecurityContext`; prefer per-test `@WithMockUser` or request post-processors; avoid static mutable auth; reset mocks/fixtures cleanly; verify tests actually executed before comparing logs.

## 18. Quick Investigation Workflow

1. **Read actual status, request, headers, handler, and resolved exception** via `print()`/`MvcResult`.
2. **Identify the test layer:** `@WebMvcTest`, `@SpringBootTest` + `@AutoConfigureMockMvc`, `standaloneSetup`, or real `RANDOM_PORT`?
3. **Check `SecurityFilterChain`:** default vs custom, imported into the slice, filters registered?
4. **If 401:** Anonymous? Which `AuthenticationEntryPoint`? Basic/form/JWT? Valid mock user/credentials?
5. **If 403 `POST`:** Check `csrf()` before checking roles. If 403 `GET`, check authorities, roles, and method security.
6. **If 404:** Test with an authenticated user, verify handler is controller vs static resource, check path/method/`contextPath` and service fixture.
7. **Is there a positive control?** An authorized user with valid input must receive 200.
8. **Compare with full context:** Do the slice and production share security config and bean semantics?
9. **Fix the actual root cause** rather than disabling security or test filters.
10. **Keep negative tests** protecting authorization, CSRF, and not-found contracts.

### Symptom Decision Tree

~~~text
Unexpected status?
   |
   +-- 401: User? Entry point? SecurityFilterChain? Basic/Bearer?
   |
   +-- 403: CSRF on unsafe method?
   |          |
   |          +-- Valid CSRF present? Roles/authorities/@PreAuthorize?
   |
   +-- 404: Cleared security filters?
              |
              +-- Controller handler? Service/data returned not found.
              |
              +-- Resource/null handler? URI/route/context path.
~~~

## 19. Run Commands and Expected Results

~~~bash
./gradlew clean test
./gradlew test --tests com.example.mockdiag.DemoControllerSecuritySliceTest
./gradlew test --tests com.example.mockdiag.FullSecurityContractTest
./gradlew test --tests com.example.mockdiag.DemoControllerSecuritySliceTest.publicPostWithoutCsrfIs403
./gradlew test --tests com.example.mockdiag.DemoControllerSecuritySliceTest.missingItemIsDomain404
~~~

On Windows use `gradlew.bat`. If the project lacks Gradle Wrapper scripts, run with an installed Gradle or generate the wrapper first; `build.gradle` does not generate `gradlew` automatically. **No `BUILD SUCCESSFUL` execution report was observed while authoring this lesson.**

| Test | Expected Evidence |
| --- | --- |
| `anonymousPublicIs200` | 200 `pong` |
| `anonymousProtectedIs401` | 401 |
| `authenticatedProtectedIs200` | 200 `alice` |
| `ordinaryUserDeniedAdmin403` | 403 |
| `adminAuthorized200` | 200 `restricted` |
| `publicPostWithoutCsrfIs403` | 403 |
| `publicPostWithCsrfIs200` | 200 JSON `hello` |
| `publicPostInvalidCsrfIs403` | 403 |
| `postProcessorCreatesAuthentication` | 200 `reader` |
| `foundItemUsesControllerAndReturns200` | 200 JSON item, controller handler |
| `missingItemIsDomain404` | 404 domain, controller handler |
| `wrongSingularPathIsRouting404` | 404 wrong URI |
| `debugMvcResultShowsMatchedDomainHandler` | 404, handler present |
| `anonymousPublicStill200` | Full context 200 |
| `anonymousProtectedStill401` | Full context 401 |
| `realServiceReturnsExistingItem` | Full context 200 |
| `realSecurityStillBlocksNonAdmin` | Full context 403 |

Expected outcomes must not be treated as real CI output; if an actual test fails, inspect the stack trace and active library/version configuration.

## 20. Anti-Patterns and Fixes

| Mistake | Why It Is Bad | Proper Fix |
| --- | --- | --- |
| Seeing 401 and setting `addFilters=false` | Bypasses security | Fix authentication/filter chain |
| `@WebMvcTest` public route 401 from default chain | Slice lacks custom config | `@Import(SecurityConfig.class)` |
| Seeing 403 `POST` and adding `ADMIN` role | CSRF token still missing | Add `with(csrf())` |
| Disabling CSRF in production because tests turned red | Alters threat model | Keep policy, test valid/invalid tokens |
| `@WithMockUser(roles="ROLE_ADMIN")` | Double-prefixed role | `roles="ADMIN"` |
| 404 `Optional.empty` yet editing controller mapping | Domain not found | Stub data, assert handler |
| Singular/plural path typo | Does not map | Fix request URI |
| Wrong HTTP method | 405 | Match `@GetMapping`/`@PostMapping` |
| Wrong `Content-Type` | 415 | `application/json` |
| `@WebMvcTest` missing service | Context fails before `@Test` | `@MockitoBean` |
| Standalone MockMvc claiming endpoint is secure | Filters absent | Wire `springSecurity()` properly |
| Mock user assumed to verify JWT signature | Never decodes token | Decoder integration test |
| Asserting HTTP status only | Hides wrong body or handler | Assert payload, handler, service |
| Using `@ControllerAdvice` for filter rejections | Filters run before MVC | `EntryPoint`/`AccessDeniedHandler` |
| Printing credentials in CI `DEBUG` logs | Leaks secrets | Redact logs |
| Class-level user on anonymous tests | False positive | Method-level auth |

## 21. Self-Check

**1.** Is an anonymous `GET` to a protected route returning 401 a bug? **No**, it often matches HTTP Basic policy.

**2.** Can form login return 302 instead of 401 for anonymous users? **Yes**.

**3.** Does 403 guarantee the user is logged in? **No**, CSRF can reject an anonymous `POST`.

**4.** Does `permitAll` disable CSRF? **No**.

**5.** Does `@WithMockUser` create a real DB user? **No**.

**6.** Does `@WithMockUser` verify JWT signatures? **No**.

**7.** What authority does `hasRole("ADMIN")` require? **`ROLE_ADMIN`**.

**8.** What authority does `roles="ADMIN"` create? **`ROLE_ADMIN`** by default.

**9.** Can a `GET` to a bad route return 401 before 404? **Yes**, security filters run first.

**10.** What does a 404 from an item controller route when the service returns empty mean? **Domain 404; routing succeeded**.

**11.** Does `@WebMvcTest` auto-scan `@Service` beans? **No**, supply a mock or fixture.

**12.** Why `@Import(SecurityConfig.class)`? **To apply custom security rules inside the MVC slice**.

**13.** Can `addFilters=false` silence 401/403? **Yes, by bypassing filters**, so it proves nothing about security.

**14.** Does MockMvc open a TCP socket by default? **No**.

**15.** Can a `POST` with the wrong `Content-Type` return 415? **Yes**, after clearing security filters.

**16.** Can a `POST` to a `GET` route return 405? **Yes**.

**17.** Can `MvcResult` prove a 404 came from the controller? **Yes**, by inspecting handler and service result.

**18.** Can `@PreAuthorize` return 403? **Yes**, when method security is enabled and the proxy executes.

**19.** With multiple `SecurityFilterChain`s, what matters? **`securityMatcher`/`@Order` select the chain; `requestMatchers` enforce URL rules**.

**20.** Where should diagnosis start? **Request, filters, principal, CSRF, handler, and `MvcResult`**.

### QA Checklist

- Distinguished `@WebMvcTest` vs full `@SpringBootTest` vs standalone MockMvc?
- Confirmed `spring-security-test` dependency and active mock user setup?
- Confirmed production `SecurityConfig` is imported in slices or loaded in full context?
- Kept `addFilters` enabled in security tests?
- Tested anonymous and authenticated scenarios separately?
- Verified role/authority names and `ROLE_` prefixes?
- Tested both negative and positive CSRF on `POST`/`PUT`/`PATCH`/`DELETE`?
- Avoided disabling CSRF just to turn tests green?
- Distinguished domain 404s from routing and static resource 404s?
- Inspected `MvcResult` handler, status, and resolved exception?
- Verified URI, `contextPath`, `servletPath`, HTTP method, and `produces`/`consumes`?
- Stubbed `@MockitoBean` service accurately in controller tests?
- Included positive 200 controls for public, user, admin, CSRF, and item paths?
- Included a full-context security contract test to catch slice drift?
- Avoided treating mock principals as real credential/JWT verification?
- Prevented leaking `SecurityContext`, sessions, or static state across tests?
- Ensured logs never expose credentials, JWTs, or CSRF tokens?
- Avoided claiming Gradle ran without real test output?

**Conclusion:** **Unexpected 401, 403, and 404 statuses in MockMvc** must be traced in order: **security filters -> authentication -> CSRF/authorization -> `DispatcherServlet` handler mapping -> controller/service/domain response**. Use **`@WithMockUser`, `with(user())`, `csrf()`, `@Import(SecurityConfig.class)`, and `MvcResult`/`print()`** intentionally, preserving both negative security tests and positive controls. Never make tests pass by stripping out security filters.

## References

- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Spring Security: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Spring Security — Setting Up MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security — Running Test as User: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — CSRF MockMvc Test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Framework 6.2 — MockMvc Framework: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Framework 6.2 — @RequestMapping: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Boot 3.4 API — AutoConfigureMockMvc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html
