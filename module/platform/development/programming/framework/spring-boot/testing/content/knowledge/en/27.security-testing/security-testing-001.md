# spring-security-test and Real Filter Chain Integration in Spring Boot Testing

## 1. The problem: a “200 OK” test does not prove an application is secure

A Spring Boot application using Spring Security may have a controller that returns the expected data, yet a test might accidentally **bypass the security layer** when invoking the controller. For example, `MockMvcBuilders.standaloneSetup(new CatalogController(...))` only sets up the MVC handler if security filters are not added. In that situation:

- An endpoint that should require authentication still returns 200 for a request without credentials.
- An account without the EDITOR role can still call the record creation API.
- A POST request without a CSRF token still succeeds even though the application configures CSRF.
- `@WithMockUser` creates a pre-populated user, preventing tests from detecting misconfigured login, password, or JWT decoder settings.
- Tests only verify the controller without checking `SecurityFilterChain`, `FilterChainProxy`, HTTP Basic/Bearer filters, or `@PreAuthorize`.

**The topic of this lesson** is using the **`spring-security-test`** library to write tests at the right layer, especially **integrating the application's real filter chain into MockMvc**. We will distinguish between:

1. **Authentication**: who is calling? Have credentials actually been verified?
2. **Authorization**: does that caller have the appropriate role/authority?
3. **CSRF and headers**: is the state-changing request valid, and are security headers attached properly?
4. **Filter-chain integration**: does the request pass through `springSecurityFilterChain` or call the controller directly?
5. **Method security**: is `@PreAuthorize` on a service enforced through the Spring AOP proxy?
6. **Test scope**: how do `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc`, and a real HTTP server differ?

This lesson uses **Java 17+, Spring Boot 3.5.x, Spring Security 6.x, JUnit Jupiter, and MockMvc**. The complete sample code includes HTTP Basic and in-memory users **for demo/testing only**; production requires an appropriate credential store, password policy, and authentication mechanism.

## 2. How does the Spring Security filter chain process a request?

In a Servlet application, Spring Security typically integrates with the servlet container via `DelegatingFilterProxy` and `FilterChainProxy` (the `springSecurityFilterChain` bean). `FilterChainProxy` selects a `SecurityFilterChain` matching the request, then executes the filters in their configured order.

```text
HTTP request or MockHttpServletRequest
             |
             v
      Servlet filter infrastructure
             |
     springSecurityFilterChain
       (FilterChainProxy)
             |
      Select SecurityFilterChain
      by securityMatcher/ordering
             |
   +---------+-----------+------------------+
   |                     |                  |
SecurityContext      Authentication      Authorization
CSRF                 HTTP Basic/Bearer   AuthorizationFilter
exception handling   credentials check    deny/allow
   |                     |                  |
   +---------------------+------------------+
             |
             v
  DispatcherServlet -> Controller -> Service
                                         |
                                  @PreAuthorize proxy
             |
             v
         HTTP response
```

This is a conceptual diagram, not a fixed-order list of filters for every configuration. The actual filters vary depending on `httpBasic`, `formLogin`, `oauth2ResourceServer`, CSRF, session management, CORS, and multiple `SecurityFilterChain` beans.

**Key takeaway:** `@WithMockUser` and `user()` can construct a pre-populated `Authentication` for tests, but **the filter chain must still be present** to verify authorization, CSRF, and exception handling. Conversely, if you want to verify that username/password are actually authenticated, you must send an **HTTP Basic header** through `BasicAuthenticationFilter` rather than only pre-populating a principal.

### 2.1. Do not confuse “security filters run” with “a real HTTP server”

`@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc(addFilters=true)` starts the Spring context and registers the application's filters with MockMvc, but **does not open an HTTP socket**. Requests are dispatched by MockMvc into a simulated Servlet API. It still tests `FilterChainProxy` and authentication/authorization/CSRF against the context's real configuration.

`@SpringBootTest(webEnvironment=RANDOM_PORT)` with `TestRestTemplate` or a real HTTP client starts an **embedded HTTP server** and sends requests over the network stack. Choose this type when you need to verify container/network behavior, cookies, redirects, TLS integration, proxy headers, or server runtime behavior. Even over real HTTP, tests must still use **test identities and an isolated database**.

## 3. Required dependency: spring-security-test

In a Spring Boot 3.5.x MVC project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The lines above are a **`build.gradle` snippet**. When using the Spring Boot BOM, do not declare a separate Spring Security version without a clear reason: mixing Spring Security 6.x test with a Spring Security 7.x runtime can cause `NoSuchMethodError` or differing behavior.

The `spring-security-test` library provides:
- `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext`.
- `SecurityMockMvcRequestPostProcessors.user()`, `httpBasic()`, `csrf()`, `anonymous()`, `jwt()`, `authentication()`.
- `SecurityMockMvcResultMatchers.authenticated()`, `unauthenticated()`.
- `SecurityMockMvcConfigurers.springSecurity()` to integrate into a manually built MockMvc.
- Test listeners that populate a mock `SecurityContext` at the right test lifecycle point and clean up state after the test.

**Do not assume the filter chain ran just because tests compile with `@WithMockUser`.** The dependency only provides utilities; the filter chain must be properly wired into the MockMvc configuration.

## 4. Which test level verifies what?

| Setup | Real controller? | Real security filters? | Credential validation via filter? | Real HTTP socket? |
|---|---|---|---|---|
| Mockito mock service/controller | No or mocked only | No | No | No |
| `MockMvcBuilders.standaloneSetup(controller)` default | Real controller | **No**, unless filters are explicitly attached | No if filters are missing | No |
| `MockMvcBuilders.webAppContextSetup(ctx).apply(springSecurity())` | Yes | **Yes** | Yes, if real headers/credentials are sent | No |
| `@WebMvcTest + MockMvc` | Controller slice | Yes when security is auto-configured/properly imported | Yes if config + filters + auth provider are included in slice | No |
| `@SpringBootTest + @AutoConfigureMockMvc(addFilters=true)` | Yes, full context | **Yes** | Yes when using `httpBasic()`/bearer header | No |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Yes, full context | **Yes** | Yes with real HTTP header/token | **Yes** |

**Important for `@WebMvcTest`:** Spring Boot 3.5 can auto-configure security test infrastructure, but a project's custom `SecurityFilterChain` or `@Service` may be excluded by slice scanning. You must `@Import` essential beans, or use a full context if the goal is to test the complete production configuration.

**Important for `@AutoConfigureMockMvc`:** the `addFilters` parameter defaults to **true**. If changed to `addFilters=false`, servlet filters in the application context are not registered with MockMvc; authorization/CSRF assertions may no longer guard the same execution path as the real application.

## 5. Security contract of the mini application

We design the API so tests separate authentication, authorization, and CSRF:

| HTTP endpoint | Policy |
|---|---|
| `GET /api/public` | Allow anonymous |
| `GET /api/items/{id}` | Requires one of `ROLE_USER`, `ROLE_EDITOR`, `ROLE_ADMIN` |
| `POST /api/items` | Requires `ROLE_EDITOR` **and** a valid CSRF token |
| `DELETE /api/items/{id}` | Requires `ROLE_ADMIN` **and** a valid CSRF token |
| `GET /api/audit` | HTTP layer requires authenticated; service also checks `@PreAuthorize("hasRole('AUDITOR')")` |
| Any other path | Deny all |

Test accounts (example only):
- `viewer / viewer-pass` has `ROLE_USER`.
- `editor / editor-pass` has `ROLE_EDITOR`.
- `admin / admin-pass` has `ROLE_ADMIN`.
- `auditor / auditor-pass` has `ROLE_AUDITOR`.

Passwords in the example are **encoded with `DelegatingPasswordEncoder`** before being placed into `InMemoryUserDetailsManager`. Production projects should not hard-code these users/passwords in an application class; the demo has no real user store connection.

The policy enables `httpBasic()` so tests can exercise real request authentication. It keeps CSRF enabled by default in the web application explicitly; **HTTP Basic does not automatically eliminate CSRF risk** in browser contexts that may attach Basic credentials automatically.

## 6. Complete Spring Boot 3.5.8 / Java 17 project

Structure:

```text
build.gradle
src/main/java/com/example/securitylab/
    SecurityLabApplication.java
    SecurityConfig.java
    AuditService.java
    CatalogController.java
src/test/java/com/example/securitylab/
    SecurityChainIntegrationTest.java
    SecurityMvcSliceTest.java
    SecurityLiveHttpTest.java
```

### 6.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot BOM manages compatible Spring/Security/JUnit versions. `spring-security-test` stays in test scope only. `@SpringBootTest` and JUnit Jupiter are integrated via `starter-test`, so you do not need to manually add `@ExtendWith(SpringExtension.class)` on properly annotated Boot tests.

Running via `./gradlew` requires a Gradle wrapper in the project; the build file above **does not generate a wrapper automatically**.

### 6.2. Application class

File `src/main/java/com/example/securitylab/SecurityLabApplication.java`:

```java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
```

### 6.3. SecurityFilterChain configuration and test identities

File `src/main/java/com/example/securitylab/SecurityConfig.java`:

```java
package com.example.securitylab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items/*")
                    .hasAnyRole("USER", "EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/items")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.DELETE, "/api/items/*")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/audit")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build(),
            User.withUsername("auditor")
                .password(encoder.encode("auditor-pass"))
                .roles("AUDITOR")
                .build()
        );
    }
}
```

**Explanation:**
- The `SecurityFilterChain` bean is the real configuration used by `FilterChainProxy`, not a Java mock.
- `authorizeHttpRequests` applies rules by HTTP method and path; `anyRequest().denyAll()` protects undeclared paths.
- `hasRole("EDITOR")` looks up authority `ROLE_EDITOR` by default; do not pass `ROLE_EDITOR` into `hasRole` when using the default prefix.
- `httpBasic` installs the filter that reads the `Authorization: Basic ...` header and authenticates via `UserDetailsService`/`PasswordEncoder`.
- `csrf` is kept enabled to test state-changing requests. In a production application, CSRF should only be disabled when the threat model confirms it is appropriate, such as a stateless bearer-only API that does not accept ambient browser credentials.
- `@EnableMethodSecurity` activates method security proxies so `@PreAuthorize` on services takes effect; HTTP URL rules **do not replace** method security.

This example runs standalone but contains **demo user credentials** in source code for instructional purposes. When deploying a real system, move credentials to a secure identity provider/store, secrets manager, and appropriate password/token policy.

### 6.4. Service using @PreAuthorize

File `src/main/java/com/example/securitylab/AuditService.java`:

```java
package com.example.securitylab;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    @PreAuthorize("hasRole('AUDITOR')")
    public String readAudit() {
        return "audit-report";
    }
}
```

This method is only permitted when `Authentication` has `ROLE_AUDITOR`. `@PreAuthorize` is enforced via a **Spring proxy**; if code directly calls `new AuditService().readAudit()` outside Spring, the annotation is not processed by AOP.

### 6.5. REST controller with an endpoint for each rule

File `src/main/java/com/example/securitylab/CatalogController.java`:

```java
package com.example.securitylab;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final AuditService auditService;

    public CatalogController(AuditService auditService) {
        this.auditService = auditService;
    }

    @GetMapping("/api/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/api/items/{id}")
    public ItemView readItem(
            @PathVariable long id,
            Authentication authentication) {
        return new ItemView(
                id, "Notebook", authentication.getName());
    }

    @PostMapping("/api/items")
    public ResponseEntity<ItemView> create(
            @RequestBody CreateItem request,
            Authentication authentication) {

        ItemView saved = new ItemView(
                101L, request.name(), authentication.getName());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(saved);
    }

    @DeleteMapping("/api/items/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/audit")
    public String audit() {
        return auditService.readAudit();
    }

    public record CreateItem(String name) {
    }

    public record ItemView(
            long id, String name, String actor) {
    }
}
```

The controller has no database: it returns deterministic data so tests focus strictly on **security controls**. In a real application, authorization may also depend on owner/tenant or per-record data; corresponding service/domain security tests are needed.

The `GET /api/items/{id}` endpoint receives `Authentication` from Spring Security's argument resolver. When a request is blocked, the MVC handler is not executed and there is no `actor` to return.

## 7. Testing the full security filter chain with MockMvc

File `src/test/java/com/example/securitylab/SecurityChainIntegrationTest.java`:

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = true)
class SecurityChainIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy securityFilterChain;

    @Test
    void securityFilterChainBeanIsPresent() {
        assertFalse(
            securityFilterChain.getFilterChains().isEmpty());
    }

    @Test
    void publicResourceAllowsAnonymousRequests() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedGetWithoutCredentialsReturns401()
            throws Exception {
        mvc.perform(get("/api/items/7"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void incorrectBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/items/7")
                .with(httpBasic("viewer", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void realBasicAuthenticationForViewerSucceeds()
            throws Exception {
        mvc.perform(get("/api/items/7")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("viewer"))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.actor").value("viewer"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void withMockUserExercisesAuthorizationWithoutPassword()
            throws Exception {
        mvc.perform(get("/api/items/9"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actor").value("alice"));
    }

    @Test
    @WithUserDetails("viewer")
    void withUserDetailsLoadsPrincipalWithoutBasicLogin()
            throws Exception {
        mvc.perform(get("/api/items/10"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actor").value("viewer"));
    }

    @Test
    void perRequestUserPostProcessorSetsUserForThisRequest()
            throws Exception {
        mvc.perform(get("/api/items/11")
                .with(user("synthetic-viewer").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actor")
                .value("synthetic-viewer"));
    }

    @Test
    void viewerCannotCreateEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("viewer", "viewer-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithValidCsrfCanCreate() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.actor").value("editor"));
    }

    @Test
    void adminDeleteWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(delete("/api/items/13")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminDeleteWithCsrfReturns204() throws Exception {
        mvc.perform(delete("/api/items/13")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    void viewerCannotDeleteEvenWithValidCsrf() throws Exception {
        mvc.perform(delete("/api/items/13")
                .with(httpBasic("viewer", "viewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void authorityWithoutRolePrefixDoesNotSatisfyHasRole()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(user("synthetic")
                    .authorities(
                        new SimpleGrantedAuthority("EDITOR")))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void methodSecurityRejectsViewerAfterHttpAuthentication()
            throws Exception {
        mvc.perform(get("/api/audit")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorPassesMethodSecurity() throws Exception {
        mvc.perform(get("/api/audit")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit-report"));
    }

    @Test
    @WithAnonymousUser
    void anonymousAnnotationStillRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/api/items/12"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUnknownPathIsDenied() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securityDefaultAddsNosniffHeader() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(
                header().string(
                    "X-Content-Type-Options", "nosniff"));
    }
}
```

### 7.1. Guarantees of the test class

This test suite verifies three separate conditions:

**A. Does the filter chain exist and execute?** The `securityFilterChainBeanIsPresent` test checks that `FilterChainProxy` has chains, but that **is not enough on its own**. The anonymous 401, missing CSRF 403, and deny-all 403 tests prove that requests are **actually governed** by the security filters according to the configuration.

**B. Real authentication via HTTP Basic?** `httpBasic("viewer", "viewer-pass")` generates `Authorization: Basic ...`, and `BasicAuthenticationFilter`/the authentication provider matches the account and encoded password. The wrong-password test must return 401 and only the right password passes with 200. That is integration of **filter + credential lookup** (though it does not test production IdP/LDAP/OIDC if the app uses those systems).

**C. Authorization or CSRF?** An editor allowed to `POST` still gets 403 when CSRF is missing/invalid. A viewer with valid CSRF still gets 403 for lacking `ROLE_EDITOR`. These two tests prevent the false assumption that every 403 has the same cause.

### 7.2. `@WithMockUser` does not check passwords

`@WithMockUser(username="alice", roles="USER")` builds a test `Authentication` and places it into `SecurityContext`; the user `alice` **does not have to exist** in `InMemoryUserDetailsManager`. It is well suited for testing **authorization/principal-based logic**, but it never verifies Basic passwords, token signatures, OAuth logins, or `UserDetailsService.loadUserByUsername`.

Similarly, `user("synthetic-viewer").roles("USER")` is a request post-processor and does not send a real username/password via HTTP Basic. `@WithUserDetails("viewer")` loads user details from the bean but **does not perform a credential check**. Therefore, use them **to complement** real login tests, not to replace them.

### 7.3. Is it necessary to check both 401 and 403?

**Yes, if that is the security contract:**
- **401 Unauthorized** is typically for unauthenticated requests or invalid credentials, accompanied by `WWW-Authenticate` when HTTP Basic challenges are required.
- **403 Forbidden** is typically for an authenticated principal with insufficient permissions, or a request missing a CSRF token when CSRF protection applies.
- In other security configurations (form login, OAuth2 login), an anonymous request may receive a **302 redirect** to the login page instead of 401. Do not copy every expected status from an HTTP Basic test into a form-login app.

Testing a user with the wrong role but valid CSRF verifies that **authorization** actually denies; testing a user with the right role but missing CSRF verifies that **CSRF** actually denies.

### 7.4. Roles and authorities in Spring Security Test

`@WithMockUser(roles="EDITOR")` or `user("x").roles("EDITOR")` typically creates `GrantedAuthority("ROLE_EDITOR")`.

If you use `user("x").authorities(new SimpleGrantedAuthority("EDITOR"))`, the user only has authority `EDITOR`, not `ROLE_EDITOR`, so `hasRole("EDITOR")` **is not satisfied** by default. Similarly, JWT tokens often carry authorities prefixed with `SCOPE_...` rather than automatically becoming `ROLE_...` unless a `JwtAuthenticationConverter` or corresponding authorization rule is configured.

In a project with a custom role prefix, use the same converter/prefix as production and test the **actual** granted authorities.

## 8. @WebMvcTest: protecting the right slice without confusing it with the full context

When you only want to test MVC controllers + security rules, `@WebMvcTest` initializes the servlet/MVC infrastructure but **does not** scan all `@Service` beans. If the controller depends on `AuditService`, you must `@Import` the real implementation or mock the dependency appropriately; and custom `SecurityConfig` must be imported to avoid falling back to a default chain that differs from production.

File `src/test/java/com/example/securitylab/SecurityMvcSliceTest.java`:

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
@Import({SecurityConfig.class, AuditService.class})
class SecurityMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousItemIsProtectedByImportedChain()
            throws Exception {
        mvc.perform(get("/api/items/4"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerLoginGoesThroughImportedChain()
            throws Exception {
        mvc.perform(get("/api/items/4")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void serviceMethodSecurityIsStillEffective()
            throws Exception {
        mvc.perform(get("/api/audit")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());
    }
}
```

With `@Import({SecurityConfig.class,AuditService.class})`, the slice has the security rules and service proxy it needs. **Note:** if the production project has multiple authentication providers, filters, tenant resolvers, or conditional configuration, a slice may not fully represent the app. When the goal is **integrating the entire system's real filter chain**, `@SpringBootTest + @AutoConfigureMockMvc` generally provides stronger evidence.

### 8.1. What happens if @WebMvcTest fails to import the right SecurityConfig?

Spring Boot may build a default security chain when the custom chain is missing from the slice. Endpoints may still return 401, causing an `anonymousIsDenied` test to produce a **false green** even though the real security config was never verified. Assert at least:
- Public endpoints are permitted.
- Valid user role endpoints return the expected response.
- Wrong role endpoints return 403.
- CSRF is enabled/disabled as intended.
- Method security if part of the use case.
- Several rules specific to the actual production configuration.

If `SecurityConfig` uses external beans outside the slice, mock/import the exact dependencies or switch to a full integration test; do not accidentally disable authentication to “fix” a context error.

## 9. Manual MockMvc setup must add springSecurity()

If you do not use Boot's auto-configured MockMvc, configure it per the Spring Security testing reference:

```java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

This is a **fragment** for use inside a JUnit setup method, with `WebApplicationContext webApplicationContext`, `MockMvcBuilders` imports, and static import `SecurityMockMvcConfigurers.springSecurity`. It requires a Spring context containing `springSecurityFilterChain`.

`apply(springSecurity())` adds the setup required for Spring Security, including `FilterChainProxy` and `TestSecurityContextHolderPostProcessor` support so `@WithMockUser`/`user()` bind properly to MockMvc requests.

**Anti-pattern:**

```java
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new CatalogController(...))
        .build();
```

This is a **non-standalone anti-pattern illustration**, with `...` representing dependencies. If you only want to test JSON mapping of a controller and deliberately choose **not** to test security, standalone setup still has value. However, do not call it a “filter chain integration test”. Calling `.with(user(...))` does not inject the entire filter chain into a MockMvc instance that has no filters.

### 9.1. Why is `@AutoConfigureMockMvc(addFilters=false)` dangerous for security tests?

It can cause:
- Protected URLs not to be blocked by the Security authorization filter.
- The CSRF filter not to run.
- Request header authentication not to be decoded/validated.
- Method security to still run if proxies were created, leading to a test returning 403 for a different reason while the HTTP filter chain was skipped.

**Therefore, test from multiple angles:** anonymous 401 on protected URLs, Basic wrong password 401, valid password 200, missing CSRF 403, and role-specific 403. A single assertion can be misleading.

## 10. CSRF: tests must verify missing, invalid, and valid tokens

For browser-authenticated flows, CSRF is an important defense for state-changing HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`). In our example, `SecurityFilterChain` has CSRF enabled.

```java
// Missing CSRF: POST returns 403 by default.
mvc.perform(post("/api/items")
        .with(httpBasic("editor", "editor-pass"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isForbidden());

// Valid CSRF in MockMvc:
mvc.perform(post("/api/items")
        .with(httpBasic("editor", "editor-pass"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isCreated());

// Invalid CSRF:
mvc.perform(post("/api/items")
        .with(httpBasic("editor", "editor-pass"))
        .with(csrf().useInvalidToken())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isForbidden());
```

The snippets above belong inside a test with `MockMvc mvc`, the static imports, and the lesson's controller/chain; they are not a standalone file.

`csrf()` adds a valid token matching the test setup; `csrf().asHeader()` sends the token via a header, and `csrf().useInvalidToken()` generates an invalid token to verify rejection behavior.

**Limitations of mock CSRF:** `.with(csrf())` does not prove the browser/UI actually obtained the token from the server and sent it back in the right cookie/header per production mechanics. For flows requiring `CookieCsrfTokenRepository`, an SPA, or a session setup, an integration test exchanging actual tokens/sessions is needed. In HTTP tests via `TestRestTemplate`, there is no `.with(csrf())`; the token must be obtained using the real web protocol.

### 10.1. CSRF and stateless Bearer APIs

A REST API that only accepts a bearer token explicitly provided by the client in the `Authorization` header, without using cookies or ambient browser auth, may have a different threat model and intentionally configure CSRF as disabled. However, do not copy `csrf.disable()` just to make POST tests pass when the application still uses session cookies, form login, or HTTP Basic from browsers.

**Proper tests** must match the real policy: if CSRF is enabled, missing/invalid tokens are rejected; if intentionally disabled, tests must confirm the API still requires authentication/authorization. Disabling CSRF **does not mean** every POST should be public.

## 11. @WithMockUser, @WithUserDetails, and different request processors

| Tool | Where does the principal come from? | Does it exercise real password/token decoder? | Primary value |
|---|---|---|---|
| `@WithMockUser(username="alice", roles="USER")` | Mock user created by Spring Security Test | **No** | Authorization, principal-based logic |
| `@WithAnonymousUser` | Anonymous authentication test context | **No** | Anonymous flow |
| `@WithUserDetails("viewer")` | `UserDetailsService` bean in context | **Does not** check supplied password | UserDetails/roles from store |
| `.with(user("alice").roles("USER"))` | Mock user for a single MockMvc request | **No** | Per-request principal/authorities |
| `.with(httpBasic("viewer","viewer-pass"))` | Authorization header going through `BasicAuthenticationFilter` | **Yes** in a Spring context with a Basic provider | Real HTTP Basic authentication integration |
| `.with(csrf())` | Test CSRF token | Unrelated to credentials | Verifying CSRF filter |
| `.with(jwt())` | JWT Authentication built in test | **Does not** verify JWT signature/decoder | Authorization by claims/authorities |
| `Authorization: Bearer token` with resource server config | Filter reads header then uses `JwtDecoder` | Goes through configured decoder | Bearer parsing and resource server integration |

**Warning about the name `@WithMockUser`:** It does not mock the entire `SecurityFilterChain`. When MockMvc has real filters, the mock principal still goes through authorization rules and CSRF just like in the application. What it **skips** is the login step and credential verification.

### 11.1. Default role configuration

`@WithMockUser` defaults to username `user` and role `USER`. Do not test an endpoint requiring ADMIN with an argumentless `@WithMockUser` and assume all roles are granted.

When using `roles={"USER","ADMIN"}`, Spring Security Test automatically adds the `ROLE_` prefix. If using a policy based on OAuth scopes or authorities without `ROLE_`, use `authorities={"SCOPE_orders.read"}` or an appropriate JWT request postprocessor, and ensure the real filter chain authorization rule matches.

### 11.2. @WithSecurityContext for custom principals

When an application needs a custom `Authentication` (tenant id, claims, domain user), you can create a meta-annotation with `@WithSecurityContext(factory=...)`. The factory builds a `SecurityContext` with the contract-matching principal/authorities, saving tests from duplicating boilerplate.

**Do not** build a custom factory just to test a `ROLE_USER`; `@WithMockUser` is usually clearer. A custom context still does not test credential validation if the factory pre-builds the `Authentication`.

## 12. Method security: a real filter chain is not enough if the method proxy is bypassed

HTTP authorization decides whether a request can enter a controller. Method security lets you enforce rules at the service layer, typically using `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, or `@PostFilter` when enabled.

In our example:
- `GET /api/audit` via URL rules only requires **authenticated**.
- `AuditService.readAudit()` has `@PreAuthorize("hasRole('AUDITOR')")`.
- `viewer` authenticates successfully with HTTP Basic but **is rejected with 403 when calling the method**.
- `auditor` has the right role and receives `audit-report`.

Method security tests are valuable when:
- The service is created by Spring as a real bean/proxy.
- `@EnableMethodSecurity` is actually configured.
- The controller calls the service **through the Spring bean**, not via `new Service()`.
- Tests cover both a sufficient-role case and an insufficient-role case.

If calling `this.securedMethod()` from within the same service under proxy-based AOP, self-invocation can bypass the advice. Review service design and test internal call paths if the business flow carries risk.

### 12.1. Testing a service without MVC

For pure method authorization logic, a Spring test can inject `AuditService` and call it directly with:
- `@WithMockUser(roles="AUDITOR")` -> returns the report.
- `@WithMockUser(roles="USER")` -> throws `AccessDeniedException`.

When testing a method directly through the bean/proxy, it verifies **method security**, but does not test servlet filters, CSRF, or HTTP 401/403 mapping. To claim the filter chain runs for real, corresponding MockMvc/HTTP tests are still required.

## 13. Real HTTP server: TestRestTemplate tests Basic authentication over a socket

To add integration evidence that does not rely on MockMvc, write a test with `RANDOM_PORT`.

File `src/test/java/com/example/securitylab/SecurityLiveHttpTest.java`:

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SecurityLiveHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void anonymousHttpRequestGets401() {
        ResponseEntity<String> response =
                http.getForEntity(
                    "/api/items/21", String.class);

        assertEquals(
                HttpStatus.UNAUTHORIZED,
                response.getStatusCode());
    }

    @Test
    void validBasicAuthWorksOverActualHttp() {
        ResponseEntity<CatalogController.ItemView> response =
            http.withBasicAuth("viewer", "viewer-pass")
                .getForEntity(
                    "/api/items/21",
                    CatalogController.ItemView.class);

        assertEquals(
                HttpStatus.OK,
                response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(21L, response.getBody().id());
        assertEquals("viewer", response.getBody().actor());
    }
}
```

What this adds over MockMvc:
- The embedded server actually listens on a random port.
- `TestRestTemplate` sends HTTP requests from the test JVM over a socket.
- The server servlet filter chain and Spring Security process the real Basic header.
- You can observe the HTTP response like an independent client.

However, this test **does not verify** production TLS/reverse proxy/gateway behavior, has no external user store, and does not perform CSRF state-changing requests. Those are additional tests when the architecture requires them.

## 14. OAuth2 Resource Server and JWT: distinguishing fake Authentication from a real Bearer filter

If the application uses a JWT Resource Server, `spring-security-test` provides a very useful `jwt()` postprocessor:

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

This is an **illustrative snippet** for an application that **already has an endpoint and `SecurityFilterChain` supporting JWT and the appropriate authority**. It does not belong to the runnable HTTP Basic demo and requires importing `SecurityMockMvcRequestPostProcessors.jwt`, `SimpleGrantedAuthority`, and security test dependencies.

**Do not misunderstand:** `.with(jwt())` creates a pre-built authentication on the request, so it **does not decode real Bearer token bytes**, nor does it verify the JWT's signature/issuer/audience or expired-token errors from a decoder.

If you want to verify that requests pass through `BearerTokenAuthenticationFilter`:
1. Configure `http.oauth2ResourceServer(oauth -> oauth.jwt(...))` on an appropriate chain.
2. Provide a `JwtDecoder` matching production config or a **test-only decoder mock**.
3. Send a real HTTP header:
   `Authorization: Bearer sample-token`.
4. Verify the decoder receives the token, the converter builds the right authorities, and the endpoint returns 200/403/401 depending on claims.
5. To test **real signature/issuer/audience**, do not mock the decoder; use signing keys/JWK test fixtures and real decoder configuration.

In Spring Boot 3.5, the dependency typically needed for a resource server is `spring-boot-starter-oauth2-resource-server`; do not drop a fake JWT test into an HTTP Basic demo and conclude the app has Bearer filtering enabled.

### 14.1. JWT roles, scopes, and converters

A JWT claim `scope="orders.read"` is normally converted by Spring Security to `SCOPE_orders.read`, whereas `hasRole("USER")` defaults to requiring `ROLE_USER`. A `.with(jwt().authorities(...))` test that assigns authorities directly can bypass the **real converter** and create a false positive if the production converter reads claims incorrectly.

Therefore, at least two test groups are needed:
- Fast **authorization rules**: `jwt()` with expected authorities.
- **Filter/decoder/converter integration**: send a Bearer header and verify a real or test-configured `JwtDecoder`/converter.

Never log real JWT/`Authorization` headers in failed assertions or trace output.

## 15. CORS, multiple filter chains, and hard-to-spot blind spots

### 15.1. Multiple SecurityFilterChain beans

An application may have one chain for `/api/**` and another for `/admin/**` or actuator. Each chain has a different `securityMatcher(...)`, `@Order`, and rules. `FilterChainProxy` selects the **first matching** chain.

Tests must send requests to each URL group and check:
- Which chain owns public endpoints?
- Is a protected endpoint accidentally swallowed by a broader chain?
- Is there any URL that matches no chain and bypasses security?
- Are each chain's CSRF/session/Bearer settings applied properly?
- Do actuator/error/static resource routes have distinct policies?

A test that merely checks that the `FilterChainProxy` bean exists **is not enough** to prove every URL is protected. Include negative cases for each critical path.

### 15.2. Security headers

Spring Security supports several response headers by default, such as `X-Content-Type-Options: nosniff`; the example includes a test checking that header. Other headers are conditional:
- `Strict-Transport-Security` normally only appears with HTTPS/appropriate secure requests; do not unconditionally assert it on default HTTP MockMvc.
- `Content-Security-Policy` should not be assumed auto-enabled; applications typically declare a policy tailored to their UI.
- CORS (`Access-Control-Allow-Origin`) depends on `Origin`, preflight, and `CorsConfiguration`.
- `X-Frame-Options` and other policies must match actual embedding needs.

Test headers against the **application's security contract**, rather than snapshotting every framework default header blindly.

### 15.3. CORS preflight is not an authentication request

A browser may send an `OPTIONS` preflight before sending the actual request. Preflight requests do not carry credentials like the actual request; if security configuration blocks all `OPTIONS` due to missing Basic auth, the application might work in Postman but fail in browsers.

When an API serves cross-origin clients, configure CORS explicitly and test:
- Allowed origin -> preflight returns valid headers/methods.
- Disallowed origin -> preflight is rejected.
- Actual request still requires authentication/authorization.
- `Access-Control-Allow-Credentials` is not arbitrarily combined with a wildcard Origin.

Do not add `permitAll(OPTIONS, "/**")` as a blanket fix without considering domain security policy and CORS processing.

## 16. @WithMockUser, SecurityContext, and test lifecycle

Spring Security Test includes `WithSecurityContextTestExecutionListener`, which sets up the test `SecurityContext` before each test method runs (or at the configured event) and cleans up afterward. Thus, two tests with different `@WithMockUser` annotations should not leak principals from a previous test when the listener functions properly.

**Do not store `SecurityContextHolder` in a static variable** and assume state is isolated automatically. In tests that spawn custom threads/executors, the `ThreadLocal`-bound `SecurityContext` is not propagated automatically unless proper wrapper/context propagation is used. This differs from Reactor Context in reactive transactions; Spring Security MVC tests mainly work with Servlet requests and thread-bound context.

Common failures include:
- Calling a method directly and asserting `SecurityContextHolder.getContext().getAuthentication()` without sending an HTTP request -> does not prove the filter chain.
- Dropping the test listener via custom `@TestExecutionListeners` replacing defaults -> `@WithMockUser` stops working.
- Using `@BeforeAll` to inspect the principal when the listener only prepares context per test -> principal is not yet present.
- Parallel test runs mutating a static security context -> cross-test state leakage.
- When needing a custom principal, `@WithSecurityContext` builds a controlled test context, but still does not replace authentication filters.

### 16.1. Pure authorization tests and credential tests should have distinct names

A helpful naming convention:
- `viewerCannotDeleteEvenWithCsrf`: tests **authorization**.
- `incorrectBasicPasswordReturns401`: tests **authentication**.
- `editorWithInvalidCsrfIsForbidden`: tests **CSRF**.
- `methodSecurityRejectsViewer`: tests **method security**.
- `securityFilterChainBeanIsPresent`: tests **infrastructure**.
- `validBasicAuthWorksOverActualHttp`: tests **HTTP integration**.

Naming by behavior and failure reason makes debugging much faster than `securityTest1`, `securityTest2`.

## 17. Session security, state, and data layer in security integration tests

The example project creates no database records. When testing security for an app with JPA/JDBC:
- `@Transactional` tests can roll back changes **on the test thread**, but a real HTTP server thread has its own transaction.
- `MockMvc` shares the application context, yet a `@Transactional(REQUIRES_NEW)` service can commit independently; cleanup must respect transaction boundaries.
- A `403` test should also verify **no side effects** occur, such as creating an order or publishing an event, if the endpoint has critical impact.
- If the app has `@PreAuthorize("#id == authentication.principal.tenantId")`, test principals/resources across tenant A/B and denial behavior, not just a valid role.
- When using session login, test `session fixation`, session invalidation/logout, and cookie attributes according to configuration if they are in the threat model.
- When using stateless JWT, test scopes/claims/expiry/audience and bearer filter configuration; do not use `@WithMockUser` to claim token validation was tested.

**Security is an end-to-end property:** correct URL authorization while a service ignores tenant ownership still leaves IDOR (accessing unauthorized resources) possible. Security filter tests are the foundation, not a replacement for business authorization tests.

## 18. Common pitfalls in security testing

| Symptom | Common cause | What to check |
|---|---|---|
| Protected endpoint returns 200 for anonymous | MockMvc lacks filters; `addFilters=false`; wrong matcher | Enable filters, test anonymous 401/403, check chain |
| All tests return 401 despite `@WithMockUser` | Missing security test listener/integration setup | `apply(springSecurity())` or Boot `@AutoConfigureMockMvc` |
| HTTP Basic passes with wrong password | Using mock principal instead of Basic header | Test `httpBasic(user,wrong)` through real filter chain |
| `@WithMockUser` test passes but production login fails | Mock principal bypasses UserDetails/decoder | Add authentication filter + credential tests |
| POST returns 403 even though user has EDITOR | Missing/invalid CSRF | Add `csrf()`; test missing vs invalid separately |
| POST returns 403 even with CSRF added | User lacks `ROLE_EDITOR` | Check authority prefix and rule |
| Anonymous API returns 302 instead of 401 | Form login redirect is enabled | Confirm entry point/authentication mechanism |
| `403` mistaken for “not logged in” | Authenticated but missing role, or CSRF failed | Test same request with role/token isolated |
| `@PreAuthorize` has no effect | Missing `@EnableMethodSecurity`; self-invocation or `new` service | Import config and use Spring bean proxy |
| `@WebMvcTest` reports missing service bean | Slice does not scan ordinary services | `@Import` required service or mock dependency |
| `@WebMvcTest` uses different security than production | Custom SecurityConfig excluded by slice | Import proper config, assert positive/negative policies |
| `NoSuchBeanDefinitionException` for `FilterChainProxy` | Security auto-config did not create chain | Check dependencies, `SecurityFilterChain` bean, and config |
| Test session state leaks across methods | Shared session/ContextHolder/static state | Use per-test lifecycle, avoid global auth state |
| Security header test fails in HTTP MockMvc | Header only added for secure requests | Check HTTPS precondition, do not assert HSTS on plain HTTP |
| JWT `.with(jwt())` test passes but real Bearer token fails | Bypassed JwtDecoder and signature/converter | Send `Authorization: Bearer` through real resource-server chain |
| JWT user role missing `ROLE_` | JWT converts to `SCOPE_` by default converter | Assert actual authorities, configure converter |
| Public GET still returns 401 | URL does not match `permitAll` or caught by another chain | Check `requestMatchers`/`securityMatcher`/order |
| `OPTIONS` preflight returns 401 | CORS not running before auth filters | Configure CORS and test preflight separately |
| `@AutoConfigureMockMvc(addFilters=false)` makes CSRF test pass | CSRF filter was removed from MockMvc | Keep `addFilters=true` for security tests |
| Test returns 403 but DB still has record | Side effect ran before authorization or another transaction committed | Check side effects after rejected requests |
| Test passes alone, fails in suite | SecurityContext/context cache/static state or shared data | Read test report, isolate test lifecycle |
| Build succeeds with no tests executed | Wrong JUnit runner, skipped, or NO-SOURCE | Verify executed method count in reports |

### 18.1. Methodical way to debug a “failing with 403” test

1. Confirm the request actually passed through **`FilterChainProxy`**.
2. Check status and reason: anonymous, authentication, authorization, and CSRF differ.
3. Check whether the test uses `@WithMockUser` or sends real `httpBasic()`/bearer headers.
4. Identify the exact authority created: `ROLE_EDITOR` differs from `EDITOR` or `SCOPE_editor`.
5. For POST/PUT/PATCH/DELETE, check CSRF configuration and the token in the request.
6. Check matchers and chain ordering: does the URL/method match the intended rule?
7. For `@PreAuthorize`, verify the proxy and method interceptor.
8. Inspect cookies/session/authorization headers and entry point, without **printing real tokens/passwords** to logs.
9. If the test hits a real HTTP server, verify base URL/port and filter mappings rather than assuming MockMvc behavior.
10. If the result is right yet the test still fails to guard a risk path, add an appropriate negative case rather than testing only the happy path.

## 19. Running tests and reading reports

From the project root containing the Gradle wrapper:

```bash
./gradlew test --tests "com.example.securitylab.SecurityChainIntegrationTest"
./gradlew test --tests "com.example.securitylab.SecurityMvcSliceTest"
./gradlew test --tests "com.example.securitylab.SecurityLiveHttpTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.securitylab.SecurityChainIntegrationTest"
.\gradlew.bat test --tests "com.example.securitylab.SecurityMvcSliceTest"
.\gradlew.bat test --tests "com.example.securitylab.SecurityLiveHttpTest"
```

If the project uses a Maven wrapper with equivalent dependencies/BOM and Surefire:

```bash
./mvnw -Dtest=SecurityChainIntegrationTest test
./mvnw -Dtest=SecurityMvcSliceTest test
./mvnw -Dtest=SecurityLiveHttpTest test
```

Inspect `build/reports/tests/test/index.html` (Gradle) or `target/surefire-reports/` (Maven) for the right module. Do not treat `BUILD SUCCESSFUL` as proof tests ran if the task status is `NO-SOURCE` or methods were skipped.

**The source code in this lesson is designed to run on Java 17+ and Spring Boot 3.5.x** when the project has the appropriate wrapper/dependencies. This document describes expected behavior; no runtime evidence exists in the current environment, so **do not claim JUnit tests have executed and passed**. For Boot 4/Security 7, check the new Boot test auto-configuration packages and API changes in the corresponding BOM before copying imports from Boot 3.5.

### 19.1. Why not use standalone javac?

The sample code uses Spring MVC, Spring Security, JUnit, and Gradle-managed dependencies. Running `javac CatalogController.java` alone will lack the framework classpath. The proper way to verify is via `./gradlew test` or Maven/Surefire with declared dependencies.

For plain Java without dependencies, `javac/java` suffices; this is an integration testing project and should be run through a build tool.

## 20. Security test review checklist

- [ ] `spring-security-test` is in test dependencies, aligned with the runtime Spring Security BOM.
- [ ] Real `SecurityFilterChain` is used; the entire authorization layer is not mocked.
- [ ] With MockMvc, `@AutoConfigureMockMvc(addFilters=true)` or manual `apply(springSecurity())`.
- [ ] At least one anonymous request is rejected on protected URLs.
- [ ] Valid and invalid credential tests go through the real authentication filter when that is the goal.
- [ ] `@WithMockUser` is used for authorization, not mistaken for password/JWT verification.
- [ ] `@WithUserDetails` uses the right `UserDetailsService` bean and is not treated as a password check.
- [ ] 401/302/403 assertions match the application's entry point.
- [ ] At least one user with sufficient role and one lacking role are tested for every sensitive endpoint.
- [ ] Role prefixes, authorities, scopes, and custom converters are verified.
- [ ] For non-safe methods, missing, invalid, and valid CSRF tokens are tested per configured policy.
- [ ] If `@PreAuthorize` is used, `@EnableMethodSecurity` is enabled and calls go through a real Spring proxy.
- [ ] `@WebMvcTest` includes the proper security config/service dependencies and does not silently fall back to the default chain.
- [ ] If there are multiple filter chains, URLs matching each `securityMatcher` and ordering rule are tested.
- [ ] Security headers/HSTS/CORS are tested per protocol/threat model, not rigid assumptions.
- [ ] With JWT, `jwt()` authority tests are separated from Bearer filter/`JwtDecoder` integration tests.
- [ ] With a real HTTP server, tests run over a random port and real client when required.
- [ ] 401/403 responses do not trigger unauthorized DB/external side effects.
- [ ] No production credentials are hard-coded and no tokens/PII are logged.
- [ ] Reports are checked to confirm the actual number of discovered and executed tests.

## 21. Official documentation for reference

- [Spring Security 6.5 — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): overview of `spring-security-test`.
- [Spring Security 6.5 — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `FilterChainProxy` and `springSecurity()`.
- [Spring Security 6.5 — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, `@WithMockUser`, `@WithUserDetails`.
- [Spring Security 6.5 — HTTP Basic Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): `httpBasic()` generating the Authorization header.
- [Spring Security 6.5 — CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `csrf()`, `asHeader()`, `useInvalidToken()`.
- [Spring Security 6.5 — Method Security Tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` when testing method security.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@SpringBootTest`, `@AutoConfigureMockMvc`.
- [Spring Boot 3.5 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): `addFilters=true` by default.
- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `SecurityFilterChain`, matchers, and filter configuration.
- [Spring Security 6.5 — Testing OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `jwt()` for authorization tests.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): threat model and CSRF policies.

**Conclusion:** `spring-security-test` offers convenient mock principals, request post-processors, and result matchers, but security tests are only meaningful when **MockMvc actually integrates the Spring Security filter chain**. Use `@SpringBootTest + @AutoConfigureMockMvc(addFilters=true)` or manual `apply(springSecurity())`, combining tests for anonymous 401, unauthorized user 403, valid/invalid Basic credentials, missing/invalid/valid CSRF tokens, and `@PreAuthorize` method security. `@WithMockUser` and `jwt()` help test authorization but **do not replace authentication/decoder tests**. When HTTP transport verification is needed, add `RANDOM_PORT` and a real client; when business ownership needs protection, add corresponding authorization/domain tests.
