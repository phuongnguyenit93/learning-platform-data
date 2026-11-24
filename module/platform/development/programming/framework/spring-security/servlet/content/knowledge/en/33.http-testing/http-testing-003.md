# RequestPostProcessor: `user`, `anonymous`, `authentication`, and `securityContext`

## 1. Why Do We Need `RequestPostProcessor` When Testing HTTP?

In **Spring Security Servlet**, an HTTP request reaching a controller typically passes through `SecurityFilterChain`: filters restore or build the `SecurityContext`, authenticate the caller, and then check authorization before letting the request enter `DispatcherServlet`. When writing tests with **Spring MVC MockMvc**, we want to accurately simulate many scenarios: a user with specific roles, an anonymous caller, a custom `Authentication`, or a pre-built `SecurityContext`.

Spring Security Test provides **`RequestPostProcessor`** implementations to modify `MockHttpServletRequest` before MockMvc executes it, especially static methods on `SecurityMockMvcRequestPostProcessors`:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.securityContext;
```

These import statements belong in a Java test. They are not a controller or a standalone program with `main`.

Short example:

```java
mockMvc.perform(get("/api/reports")
        .with(user("alice").roles("READER")))
    .andExpect(status().isOk());
```

**Key point:** `user(...)` and `authentication(...)` typically **pre-populate an authenticated state for the test request**. They **do not** invoke `AuthenticationManager` to check passwords, query a user database, or verify JWT signatures. To test a real login/authentication mechanism, you must execute the corresponding HTTP flow (for example `httpBasic`, form login, or a bearer token passing through `JwtDecoder`) against the real filter chain configuration.

## 2. What Mechanism Is `RequestPostProcessor`?

`RequestPostProcessor` belongs to Spring Test and has the conceptual contract:

```java
MockHttpServletRequest postProcessRequest(MockHttpServletRequest request);
```

It receives the simulated request created by MockMvc, modifies it, and returns it so the test pipeline continues. Spring Security Test supplies specialized processors for identity, headers, credentials, CSRF, and more.

Three layers must be distinguished:

1. **Request building:** `MockMvcRequestBuilders.get("/...")`, `post("/...")`, and body/header data.
2. **Request post-processing:** `.with(user(...))`, `.with(anonymous())`, `.with(authentication(...))`, `.with(securityContext(...))`.
3. **Pipeline execution:** the filter chain integrated with MockMvc, followed by the handler/controller and result matchers checking status/body/redirect.

Simulated flow:

```text
MockMvc.perform(...)
    |
    +-- MockHttpServletRequest
    |      |
    |      +-- RequestPostProcessor
    |             user / anonymous /
    |             authentication / securityContext
    |
    v
Spring Security FilterChain
    |
    +-- SecurityContext is used for the request
    +-- AuthorizationFilter checks permissions
    |
    v
DispatcherServlet / Controller
    |
    v
MockMvc ResultMatchers: 200 / 401 / 403 / body / ...
```

If MockMvc is **not** properly integrated with Spring Security, processors may not produce the expected effect: controller tests can pass without actually checking URL authorization. With Boot, `@SpringBootTest` + `@AutoConfigureMockMvc` normally auto-configures security filters; with a manually built MockMvc, use the `springSecurity()` configurer as shown later.

## 3. `user(...)`: Attaching a Simulated Principal and Authorities

Use `user(String username)` when you need a request treated as coming from an authenticated user. Example:

```java
mockMvc.perform(get("/api/reports")
        .with(user("alice").roles("READER")))
    .andExpect(status().isOk());
```

With `.roles("READER")`, Spring Security Test creates the authority **`ROLE_READER`**. Thus the following configuration permits it:

```java
.requestMatchers("/api/reports").hasRole("READER")
```

`hasRole("READER")` normally looks for the authority `ROLE_READER`, not the plain string `READER`.

Several variants:

```java
// Default when passing only username: user gets ROLE_USER.
.with(user("alice"))

// Attach one or more roles; the ROLE_ prefix is added by roles(...).
.with(user("alice").roles("READER", "EDITOR"))

// Attach authorities with exact names, without auto-adding ROLE_.
.with(user("alice").authorities(
        new SimpleGrantedAuthority("REPORT_EXPORT")))

// Use a UserDetails instance constructed by the test.
.with(user(testUserDetails))
```

These lines are **expression fragments**, placed inside `mockMvc.perform(...)` with `SimpleGrantedAuthority` imported and a `testUserDetails` variable already created. Do not chain `.roles(...)` and `.authorities(...)` without checking how the final call mutates the authority list; usually choose one explicit authority contract.

**Do not misunderstand `user("alice")` as "look up alice in `UserDetailsService`"**. Even if `alice` does not exist in the database or in-memory store, this processor still builds a principal for the test. That is an advantage for **authorization unit/integration tests**, but it proves nothing about passwords, account locks, MFA, or active authentication providers.

## 4. `anonymous()`: Testing Unauthenticated Callers

`anonymous()` creates an anonymous authentication scenario in the MockMvc request:

```java
mockMvc.perform(get("/api/reports")
        .with(anonymous()))
    .andExpect(status().isUnauthorized());
```

In the sample configuration using HTTP Basic on an endpoint requiring authentication, `401 Unauthorized` is the right expectation. However, **status depends on `AuthenticationEntryPoint`**: a form-login app may redirect to the login page instead of returning 401; a custom error handler may respond differently.

Anonymous authentication typically has principal `"anonymousUser"` and an authority like `ROLE_ANONYMOUS`. Do not look solely at `Authentication#isAuthenticated()` to infer the caller is logged in: an `AnonymousAuthenticationToken` can report true under the token contract, yet `AuthenticationTrustResolver` and rules like `.authenticated()` still treat anonymous callers as unauthenticated for authorization.

`anonymous()` is especially helpful to:

- Ensure private routes do not leak content to unauthenticated callers.
- Override a test that uses a default `@WithMockUser` or `defaultRequest(user(...))`.
- Verify public endpoints truly allow anonymous access.
- Verify the controller does not pick up an `Authentication` from a previous request in the same test suite.

Distinguish **anonymous** from **sending no Authorization header**: the two cases often result in the same rejection, but are not strictly identical when an application has custom filters, sessions, cookies, or security context handling.

## 5. `authentication(...)`: Injecting a Pre-Built `Authentication` into the Request

`authentication(Authentication)` is used when you want to test a custom authentication object, principal/credential details, token type, or authority list that the `user(...)` DSL cannot express.

Example using an authenticated `UsernamePasswordAuthenticationToken`:

```java
Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
        "carol",
        "not-used-in-this-test",
        List.of(new SimpleGrantedAuthority("AUDIT_READ")));

mockMvc.perform(get("/api/audit")
        .with(authentication(auth)))
    .andExpect(status().isOk());
```

This snippet assumes imports:

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
```

`authentication(auth)` does not send `"not-used-in-this-test"` to a user store for verification. It **uses the exact `Authentication` passed by the test**. Deliberately choose `isAuthenticated`, principal, and authorities so you do not accidentally make a test "green" with an overly privileged fake token.

When to use it:

1. An `Authentication` that is not username/password, such as one carrying extra details.
2. Principal is a custom domain object or custom `UserDetails`.
3. Needing to verify how a service/controller handles `Authentication#getName()` and authorities per a specific contract.
4. Testing authorization for a set of `GrantedAuthority` values not following the `ROLE_` convention.

If the goal is **testing a real JWT Resource Server**, attaching a pre-built `JwtAuthenticationToken` via `authentication(...)` **skips decoding and signature verification**; you must have separate tests passing through `BearerTokenAuthenticationFilter`/`JwtDecoder`.

## 6. `securityContext(...)`: Testing with a Full `SecurityContext`

`securityContext(SecurityContext)` takes a pre-constructed context, typically:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                "dave",
                "unused",
                List.of(new SimpleGrantedAuthority("ROLE_READER"))));

mockMvc.perform(get("/api/reports")
        .with(securityContext(context)))
    .andExpect(status().isOk());
```

Corresponding imports:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
```

Practical differences:

- `authentication(...)`: attaches **an `Authentication` object** so Spring Security Test creates/uses the necessary context.
- `securityContext(...)`: passes the **entire `SecurityContext`**, useful when you want to prepare a context with a specific authentication or use a custom context implementation.
- `user(...)`: the most convenient option when you only need a user, roles, authorities, and username.
- `anonymous()`: the cleanest way to explicitly specify an anonymous request.

**Do not call** `SecurityContextHolder.getContext().setAuthentication(...)` directly on the test thread assuming it will carry into every MockMvc request. Use request processors or test annotations to scope each request properly. Spring Security Test's context setup requires filter chain/test context integration; mutating `ThreadLocal` directly in the wrong place easily creates order-dependent tests.

## 7. Quick Selection Table

| Goal | Processor | What is simulated |
| --- | --- | --- |
| Authenticated user with simple roles | `user("alice").roles("READER")` | UserDetails + `ROLE_READER` |
| User with non-`ROLE_` authorities | `user("alice").authorities(...)` | Exact `GrantedAuthority` instances |
| Request treated as anonymous | `anonymous()` | Anonymous authentication |
| Custom Authentication | `authentication(auth)` | The exact constructed `Authentication` |
| Custom context | `securityContext(ctx)` | Test-supplied `SecurityContext` |
| Real HTTP Basic test | `httpBasic("alice", "password")` | HTTP Authorization header processed by Basic filter |
| Real session/form login test | `formLogin()` or valid login request | Authentication flow through filter/provider |
| CSRF test | `csrf()` | CSRF token for state-changing requests |

**Warning:** `user`, `authentication`, and `securityContext` are primarily useful for testing **authorization** and **how controllers/services consume identity**. They do not replace tests for `AuthenticationProvider`, JWT decoder, password encoder, MFA, cookie/session fixation, or OIDC login.

## 8. Spring Boot 3.3.x + Java 17: Runnable Demo Application

The example below uses **Spring MVC Servlet** and `spring-security-test`. We build a small API with three endpoints:

- `GET /public/ping`: public.
- `GET /api/reports`: requires role `READER`.
- `GET /api/audit`: requires authority `AUDIT_READ`.

The processors are tested via MockMvc, while `httpBasic(...)` is used for comparison to highlight the difference between **attaching a simulated principal** and **real authentication through an HTTP filter**.

### 8.1. Project Structure

```text
mockmvc-security-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/mocksec/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ExampleController.java
    │   └── resources/application.yml
    └── test/java/demo/mocksec/RequestPostProcessorTest.java
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

Using loopback for local HTTP Basic demo. On real networks, HTTP Basic transmits credentials in Base64, **not encrypted**; you must use HTTPS and production-appropriate authentication mechanisms.

### 8.2. Bootstrap Class

Create `src/main/java/demo/mocksec/DemoApplication.java`:

```java
package demo.mocksec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.3. SecurityFilterChain and User Store

Create `src/main/java/demo/mocksec/SecurityConfig.java`:

```java
package demo.mocksec;

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
public class SecurityConfig {

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                                .hasRole("READER")
                        .requestMatchers(HttpMethod.GET, "/api/audit")
                                .hasAuthority("AUDIT_READ")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Rules:

- `/public/ping` does not require login.
- `/api/reports` requires `ROLE_READER`.
- `/api/audit` requires exact authority `AUDIT_READ`.
- Other routes are denied by default.
- User `alice` is in the in-memory user store with the demo password; `phantom`, `carol`, and `dave` do not exist.

`{noop}` is an illustrative format for unhashed passwords, **never for production**. This is a demo configuration to show HTTP Basic actually checking the user store, not a real-world password storage design.

### 8.4. Controller Returning Minimal Output

Create `src/main/java/demo/mocksec/ExampleController.java`:

```java
package demo.mocksec;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ExampleController {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping("/api/reports")
    public Map<String, Object> reports(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "canReadReports", true);
    }

    @GetMapping("/api/audit")
    public Map<String, Object> audit(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "canReadAudit", true);
    }
}
```

The controller runs only after the rules in `SecurityFilterChain`. In tests, when a processor supplies a valid principal per the rule, the response reflects `Authentication#getName()` received by Spring MVC. Never return credentials or the entire security context to the client.

## 9. Runnable Test Suite: All Four RequestPostProcessors

Create `src/test/java/demo/mocksec/RequestPostProcessorTest.java`:

```java
package demo.mocksec;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.securityContext;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestPostProcessorTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void userWithReaderRoleCanReadReport() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(user("alice").roles("READER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.canReadReports").value(true));
    }

    @Test
    void fakeUserCanReadViaPostProcessorEvenWhenAbsentFromStore()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .with(user("phantom").roles("READER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("phantom"));
    }

    @Test
    void anonymousCallerCannotReadPrivateReport() throws Exception {
        mvc.perform(get("/api/reports").with(anonymous()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void userWithoutReaderRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(user("mallory").roles("VIEWER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void customAuthenticationCanCarrySpecificAuthority()
            throws Exception {
        Authentication auth =
                UsernamePasswordAuthenticationToken.authenticated(
                        "carol",
                        "unused",
                        List.of(new SimpleGrantedAuthority("AUDIT_READ")));

        mvc.perform(get("/api/audit").with(authentication(auth)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("carol"))
                .andExpect(jsonPath("$.canReadAudit").value(true));
    }

    @Test
    void fullSecurityContextCanBeSuppliedForOneRequest()
            throws Exception {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        "dave",
                        "unused",
                        List.of(
                                new SimpleGrantedAuthority("ROLE_READER"))));

        mvc.perform(get("/api/reports").with(securityContext(context)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("dave"));
    }

    @Test
    void realHttpBasicChecksPasswordAndConfiguredUserStore()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/api/reports")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                        .with(httpBasic("phantom", "anything")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointWorksForAnonymous() throws Exception {
        mvc.perform(get("/public/ping").with(anonymous()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("pong"));
    }
}
```

Run the test suite:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

The tests are expected to pass when the Gradle wrapper, JDK 17, and compatible dependencies are installed. Gradle log lines vary by version/environment, so no fixed stdout is claimed. What matters is the **passing test status**; if any failure occurs, inspect the test stack trace and security integration setup rather than "fixing" it by disabling the filter chain.

**What the test suite proves:**

1. `user("alice").roles("READER")` creates an identity with the right authority for the rule.
2. `user("phantom")` still passes because the processor **does not query** the in-memory user store.
3. `anonymous()` is rejected on private routes yet permitted on the public route.
4. `user("mallory").roles("VIEWER")` has a simulated user lacking the role and therefore gets 403.
5. `authentication(auth)` supplies the custom `AUDIT_READ` authority.
6. `securityContext(context)` passes the full context so the route reads `ROLE_READER`.
7. `httpBasic(...)` actually sends credentials through the Basic filter and user store, so wrong passwords and nonexistent users receive 401.

Thus one suite tests not only "200 when having role", but also proves **the difference between mock authentication and real authentication**.

## 10. Interpreting 401 and 403 Accurately

For an API using HTTP Basic like the example:

| Request state | Typical result | Why |
| --- | --- | --- |
| No authentication, protected route | `401 Unauthorized` | Login/authentication required |
| `anonymous()` on protected route | `401 Unauthorized` | Anonymous does not satisfy `.hasRole` or `.authenticated()` |
| Simulated user already authenticated but lacking `ROLE_READER` | `403 Forbidden` | Authentication present, authorization insufficient |
| `user("alice").roles("READER")` | `200 OK` | Matching authority |
| HTTP Basic header with wrong password | `401 Unauthorized` | `AuthenticationProvider` rejects credentials |
| `user("phantom").roles("READER")` | `200 OK` in test | Mock principal attached, user store not queried |

These statuses belong to **this specific demo configuration**. With form login, SSO/OIDC, a custom entry point, an API gateway, or an `AccessDeniedHandler`, you may get `302`, `401`, `403`, or a different response format. Tests must verify **the application's contract**, rather than forcing every system to the same status.

A common diagnostic mistake: a test uses `.with(user(...))` and assumes it verified the password encoder or disabled-account checks. No; the simulated token already holds authorities before the filter chain checks authorization.

## 11. Testing Permissions with `roles` and `authorities`

Spring Security distinguishes two checks:

```java
.hasRole("READER")
.hasAuthority("REPORT_EXPORT")
```

By convention, `hasRole("READER")` looks for `"ROLE_READER"`. `hasAuthority("REPORT_EXPORT")` looks for the exact string `"REPORT_EXPORT"`.

In tests:

```java
.with(user("alice").roles("READER"))
```

differs from:

```java
.with(user("alice").authorities(
        new SimpleGrantedAuthority("REPORT_EXPORT")))
```

If you write:

```java
.with(user("alice").authorities(
        new SimpleGrantedAuthority("READER")))
```

the result **will not** satisfy `hasRole("READER")` because the `ROLE_` prefix is missing. This is a very frequent test mistake when applications mix JWT scopes (`SCOPE_orders.read`), roles (`ROLE_ADMIN`), and business permissions (`REPORT_EXPORT`).

Do not add the prefix twice: `.roles("ROLE_READER")` is not the standard way to supply role `READER` in the DSL. Instead, use `.roles("READER")` or `.authorities(new SimpleGrantedAuthority("ROLE_READER"))`.

## 12. How Do `@WithMockUser` and RequestPostProcessor Differ?

Spring Security Test also provides the annotation:

```java
@WithMockUser(username = "alice", roles = "READER")
@Test
void example() throws Exception {
    mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
}
```

This is a **snippet inside a JUnit test class**, requiring imports for `org.springframework.security.test.context.support.WithMockUser`, `@Test`, `MockMvc`, and `MockMvcRequestBuilders`.

Comparison:

- `@WithMockUser` prepares the security context at the test method/class scope; convenient when multiple requests in a test share the same identity.
- `.with(user(...))` sets the identity for **one specific MockMvc request**, convenient for testing multiple users/authorities within a single test.
- `.with(anonymous())` can override a simulated user state to test an unauthenticated request.
- `@WithUserDetails` loads `UserDetails` from the service to simulate a real user; it is still a test aid and does not imply password verification through an authentication filter.
- When making multiple requests in one test, explicitly scope each request's identity to avoid tests depending on leftover state.

Do not view annotations and processors as two additive authentication layers. They are **ways to prepare the test security context**, with precedence by scope and per-request override.

## 13. Integrating MockMvc with the Real `SecurityFilterChain`

**Spring Boot full integration tests** typically configure:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ApiTest {
    @Autowired MockMvc mockMvc;
}
```

`@AutoConfigureMockMvc` uses the Spring application context and appropriate filter beans; the section 9 example relies on this mechanism to run real authorization rules.

If **building MockMvc manually** from `WebApplicationContext`, integrate Spring Security:

```java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

This is a **snippet inside a test method/setup** with a `context` variable of type `WebApplicationContext`, importing `MockMvcBuilders` and `SecurityMockMvcConfigurers.springSecurity`. It ensures the security filter chain and Spring Security Test support participate in the request.

If you use `MockMvcBuilders.standaloneSetup(controller)`, only the controller is registered minimally; the Spring Security filter chain **does not appear automatically**. That works for pure MVC unit tests, yet is **insufficient** to conclude `hasRole`/`hasAuthority` works. To test security, prefer context-based MockMvc or manually attach the proper security filter chain with all required dependencies.

A test with request processors but no security filters can still be misleading: a controller returning data does not mean the endpoint is protected.

## 14. Using `defaultRequest(...)` and Per-Request Overrides

When many requests in a suite share one user, you can set a default request:

```java
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
        .defaultRequest(get("/").with(user("alice").roles("READER")))
        .apply(springSecurity())
        .build();
```

This is a **setup snippet**, not a standalone file; it needs imports for MockMvc builders, HTTP builder, `user`, and `springSecurity`. For any single request, you can still override the identity:

```java
mvc.perform(get("/api/reports").with(anonymous()))
        .andExpect(status().isUnauthorized());
```

The point is **request-specific override** to test negative scenarios. If a test expects anonymous yet receives 200 because the default user remained active, inspect the composition order of request processors, setup methods, cookies/sessions, and context annotations.

Do not reuse the same `SecurityContext` instance if it could be mutated across parallel tests. Create a fresh context per scenario rather than storing an ADMIN context in a static field where tests unintentionally share state.

## 15. CSRF, Method Security, and Other Mechanisms

A request carrying a simulated principal does not mean a POST request passed CSRF. In Spring Security Servlet with CSRF protection:

```java
mockMvc.perform(post("/api/items")
        .with(user("alice").roles("EDITOR"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"demo\"}"));
```

This is an **illustrative snippet**, assuming `/api/items` and its permissions are configured; imports for `csrf`, `MediaType`, and `post` are required. If you omit `.with(csrf())`, a POST using cookies/sessions can be blocked with 403 **due to CSRF**, even when the user has the right role. Do not disable CSRF just to turn tests green when a web app still uses automatically attached credentials.

Similarly:

- Method security via `@PreAuthorize` requires `@EnableMethodSecurity` and calling the service through a Spring proxy. `.with(user(...))` prepares the identity; it does not trigger method interception by itself.
- When checking object/tenant ownership, role `READER` is only part of the check; the service must verify the specific `ownerId`/tenant.
- For a JWT Resource Server, test the converter/decoder separately rather than always constructing a pre-built `Authentication` and concluding JWT security works.
- If the app uses sessions, multi-request and cookie tests must intentionally simulate persistence; a `RequestPostProcessor` does not prove session storage is secure.
- If the app uses async Servlet, `asyncDispatch` is needed when checking the final response, and note that `SecurityContext` may require context propagation to worker threads.

## 16. Do Not Use Mock Principals to Prove Real Login

Three testing levels must be kept separate:

### A. Authorization-focused test

```java
mvc.perform(get("/api/reports")
        .with(user("alice").roles("READER")))
    .andExpect(status().isOk());
```

Goal: whether the `hasRole("READER")` rule permits access for a caller holding that authority.

### B. Authentication-focused test

```java
mvc.perform(get("/api/reports")
        .with(httpBasic("alice", "demo-only")))
    .andExpect(status().isOk());
```

Goal: Basic filter, `AuthenticationManager`, `UserDetailsService`, and `PasswordEncoder` configuration work together, at least at this test context level. Add negative cases for wrong passwords and locked accounts.

### C. End-to-end production-like test

Testing through a real HTTP server/gateway, TLS, real session/OIDC/JWT provider or signed fixtures, proxy headers, and configured database. MockMvc does not simulate full container networking or external identity providers.

If a test only uses `.with(authentication(jwtAuth))`, it does not prove JWT signatures or issuer/audience are validated. If it only uses `.with(user(...))`, it does not prove the authentication provider accepts the account. If it only uses `httpBasic`, it does not prove OAuth2 login or multi-tenant data isolation.

## 17. Common Mistakes

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `.with(user("alice"))` returns 200 even though `alice` is not in DB | Processor does not query the user store | Use real auth flow for credentials, mocks for authorization |
| `.with(user(...).roles("ADMIN"))` still gives 403 | Rule requires a different authority or object/tenant check | Inspect `SecurityFilterChain` and `GrantedAuthority` carefully |
| `.with(user(...).authorities("ADMIN"))` fails `hasRole("ADMIN")` | Missing `ROLE_` prefix | Use `.roles("ADMIN")` or `SimpleGrantedAuthority("ROLE_ADMIN")` |
| `anonymous()` gets redirect instead of 401 | App uses form login | Check entry point and route contract |
| Under-privileged user gets 401 instead of 403 | Authentication context not installed or wrong filter chain | Check MockMvc security integration |
| Test always returns 200 even without role | Test uses `standaloneSetup` without filters | Use `WebApplicationContext` + `springSecurity()` |
| `securityContext(ctx)` has no effect on controller | Security filters/test support not integrated | Check setup and how the context was created |
| Tests PASS yet production login FAILS | All tests used `.with(user(...))` | Add authentication-focused and E2E tests |
| POST returns 403 even with role | Missing CSRF token or custom access policy | Check CSRF, method, and headers |
| JWT test passes yet invalid real tokens are rejected | Mocked JWT `Authentication`, bypassed decoder | Test decoding/validation or requests through the bearer filter |
| Two tests mix up users | Shared `SecurityContext`/session/test fixture | Use request-specific processors and isolation |
| Wrong authorities after switching OIDC provider | Role/scope mapping untested | Test converter, issuer/audience/claims with proper fixtures |

### Debug Order

1. Confirm you are testing the **right endpoint, HTTP method, and `SecurityFilterChain`**.
2. Confirm MockMvc has Spring Security integrated (`@AutoConfigureMockMvc` or `springSecurity()`).
3. Confirm whether the request uses a mock identity or real credentials; never confuse the two.
4. Inspect `Authentication#getName`, `isAuthenticated`, and `getAuthorities` **in tests/internal logs**, never logging passwords/tokens.
5. Determine whether 401 comes from missing authentication or 403 from authorization/CSRF.
6. For a custom `Authentication`, check the `authenticated` flag and authority prefixes.
7. For method security, check proxy/interception and resource ownership conditions.
8. Add negative tests before loosening Security config.

## 18. Protecting Test Quality and Independence

Useful principles:

- Each test should make clear **which identity is simulated** and **which rule is verified**.
- Separate authorization tests, authentication mechanism tests, and E2E tests; never let one group substitute for another.
- Use `.with(anonymous())` to test denial paths, not only happy paths.
- Verify exact `ROLE_`/`SCOPE_`/custom authorities rather than checking only a username.
- Use `securityContext(...)` when needed; for simple cases, `user(...)` keeps tests concise and less error-prone.
- Construct fake `Authentication` objects with minimal authorities; do not grant ADMIN to every request.
- Never take a username from a client request header and construct a trusted `Authentication` without verified authentication/proxy boundaries.
- Do not print passwords, tokens, or full `SecurityContext` dumps to logs.
- If tests use fixed time/random IDs, control clocks/test data so results are repeatable.
- When running tests in parallel, avoid sharing `SecurityContextHolder`, sessions, or static mocks across tests.
- Verify HTTP status, body, object-level permissions, and error contract payload where valuable.

## 19. Practice Exercises

### Exercise 1: Roles and Permissions

Add a `GET /api/export` route requiring `hasAuthority("REPORT_EXPORT")`. Write a test for:

- A user with `ROLE_READER` but lacking `REPORT_EXPORT` → rejected.
- A user with exact `REPORT_EXPORT` via `.with(user("alice").authorities(...))` → allowed.
- An anonymous user → denied access.

Goal: distinguish `roles()` and `authorities()`.

### Exercise 2: Custom Context and Principal

Create an `Authentication` whose principal is a `UserDetails` carrying `tenantId`. Use `authentication(...)` and `securityContext(...)` in two separate tests to verify the controller/service reads the right tenant from the principal. Then test that another tenant cannot view the current tenant's data.

Goal: avoid relying solely on `getName()` when object permissions belong to a tenant.

### Exercise 3: Real vs. Mock Authentication

Given an in-memory store containing only `alice`. Use `user("phantom")` to confirm the authorization rule lets `phantom` with `ROLE_READER` through in the test; then use `httpBasic("phantom","anything")` to confirm the provider **does not** log `phantom` in. Write a comment explaining why both expectations are simultaneously true.

Goal: distinguish injecting a security context from verifying credentials.

## Takeaways

`RequestPostProcessor` in Spring Security Test helps MockMvc build **an HTTP request with a controlled security state**. `user(...)` is handy for simulated users/roles; `anonymous()` tests unauthenticated callers; `authentication(...)` attaches a custom `Authentication`; `securityContext(...)` attaches an entire `SecurityContext`. These processors are especially helpful for **authorization tests**, yet **do not prove** that passwords, JWTs, OIDC, or account policies are genuinely authenticated. To test properly, integrate `SecurityFilterChain` into MockMvc, distinguish 401 from 403, add negative tests, and test real authentication flows separately.