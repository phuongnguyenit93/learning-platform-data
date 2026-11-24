# Integrating spring-security-test with MockMvc or WebTestClient

## 1. Goal: testing login and security boundaries, not just HTTP status

In a Java/Spring Boot application, testing that an endpoint returns `200 OK` does not prove that authentication or authorization is working correctly. A controller can return valid content in a test because security filters were skipped; a request with a mocked principal can be allowed even when the password encoder, authentication provider, or token decoder is misconfigured.

**`spring-security-test`** provides tools to plug Spring Security into HTTP tests and build security contexts in a controlled way. Two common branches:

- **`MockMvc`**: for the Spring MVC/Servlet stack; integrates the Spring Security filter chain via `springSecurity()` or `@AutoConfigureMockMvc` with filters enabled.
- **`WebTestClient`**: can test HTTP in a reactive style; in a **Spring WebFlux** application, apply `SecurityMockServerConfigurers.springSecurity()` and the reactive `mockUser()`, `mockJwt()`, `csrf()`. Spring Framework also provides a WebTestClient adapter for testing MVC; **do not confuse the MVC adapter with WebFlux security mutators**.

This lesson focuses on **real login, mocked users, anonymous/forbidden, CSRF, role/authority, JWT/OIDC testing, and choosing the right test layer**.

Goal after this lesson: you can write tests proving that `formLogin()` actually invokes the authentication provider, while `user()` or `@WithMockUser` only creates a pre-built authentication to test **authorization**, and know when you need to test JWT signature/issuer/audience with a real decoder instead of mocked `jwt()`.

## 2. Separating test layers to know what each test proves

| Test layer | Tools | What is verified | What is NOT automatically proven |
|---|---|---|---|
| Small logic unit test | JUnit 5, Mockito | A function/validator/service with mocked dependencies. | SecurityFilterChain, request parsing, session/CSRF. |
| Controller + security slice | `@WebMvcTest`, `MockMvc`, `spring-security-test` | MVC mapping, imported filter chain, role/CSRF per test config. | Any production DB/provider/IdP if they are mocked. |
| Servlet security integration | `@SpringBootTest` + `@AutoConfigureMockMvc` | Multiple application beans together with the security chain, real form login and handlers in the test context. | External infrastructure or production reverse proxy. |
| Reactive web security integration | `WebTestClient.bindToApplicationContext` + `springSecurity()` | WebFlux `SecurityWebFilterChain`, reactive principal, CSRF, and route policy. | MVC servlet filters or production gateway. |
| Live-server HTTP integration | `WebTestClient.bindToServer` / TestRestTemplate | HTTP behavior over a real port, cookies, redirects, headers in the test environment. | Third-party protocols if still mocked. |
| Real OAuth/JWT integration | decoder/introspection/IdP test fixture | Signature, issuer, audience, expiry, claims mapping, and failure paths. | Cannot be achieved by mocked `jwt()` alone. |

**Test naming principle:** `withMockUserCanRead` rather than `passwordLoginWorks`. A test name should state precisely which path is being executed.

### Boundary diagram

~~~text
MockMvc (Servlet)
   |
   +-- MockHttpServletRequest
   +-- FilterChainProxy / SecurityFilterChain
   +-- UsernamePasswordAuthenticationFilter
   +-- AuthenticationManager / UserDetailsService / PasswordEncoder
   +-- Spring MVC Controller
   +-- MockHttpServletResponse

WebTestClient (WebFlux security)
   |
   +-- MockServerWebExchange
   +-- SecurityWebFilterChain
   +-- ReactiveAuthenticationManager / reactive auth providers
   +-- WebFlux Handler / Controller
   +-- Flux/Mono response verification
~~~

`MockMvc` does not open a TCP socket; it sends a mock servlet request through Spring MVC infrastructure. `WebTestClient` can bind directly to a context/controller without a socket or bind to a real server; **the binding type determines which infrastructure parts are executed**.

## 3. Dependencies: required libraries

With Spring Boot 3.x / Spring Security 6.x and Java 17+, use Spring Boot dependency management so Spring/Security versions do not drift between runtime and test.

Maven dependencies for a **Servlet Spring MVC** project:

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

**`spring-boot-starter-test` must not be treated as a replacement for `spring-security-test`**. The test starter adds JUnit, AssertJ, Mockito, and Spring Test; `spring-security-test` brings request post-processors, result matchers, annotations, and reactive test configurers.

Gradle Groovy equivalent:

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

For **WebFlux**, replace the web starter with `spring-boot-starter-webflux`, while keeping the security starter, test starter, and `spring-security-test`. Do not put servlet and reactive starters together just to use both test APIs; by default Spring Boot may choose MVC if both are present. Determine first whether **the real application is MVC or WebFlux**.

If the project uses Spring Security 7/Spring Boot 4, check the documentation for the exact version, package/API, and new modules; the examples here follow the familiar API paths of Spring Boot 3.x/Security 6.x.

## 4. Choosing MockMvc or WebTestClient based on the real runtime

| Question | Recommended choice |
|---|---|
| App uses `spring-boot-starter-web`, servlet filters, Spring MVC controllers? | **MockMvc** + servlet `springSecurity()`. |
| App uses `spring-boot-starter-webflux`, `SecurityWebFilterChain`? | **WebTestClient** + reactive `springSecurity()`. |
| Want to call the API over real HTTP, testing cookie/redirect/network boundaries? | `WebTestClient.bindToServer()` or another HTTP test client. |
| Want to test an MVC controller but prefer WebTestClient's fluent API? | Spring Framework supports the `MockMvcWebTestClient` adapter; **security is still servlet**. |
| Want to verify username/password genuinely goes through the provider? | Send real HTTP form login/basic auth, do not use `user()`/`mockUser()`. |
| Want to focus on endpoint permissions with an existing principal/scope? | `user()`, `@WithMockUser`, `jwt()` / `mockJwt()` are appropriate. |
| Want to verify JWT signature, `aud`, `iss`, `exp`? | Test `JwtDecoder`/resource server with a real signed token or an intentional fake server. |

`MockMvc` and reactive `WebTestClient` can both test security well, but **the test helper API does not turn a Servlet runtime into Reactor/WebFlux or vice versa**.

## 5. Setting up MockMvc to run real Spring Security filters

The Spring Security documentation instructs:

~~~java
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;

@BeforeEach
void setUp() {
    mvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .apply(springSecurity())
            .build();
}
~~~

Additional imports: `org.springframework.test.web.servlet.setup.MockMvcBuilders`, `org.springframework.web.context.WebApplicationContext`, and JUnit `@BeforeEach`. The code is a snippet inside a test class that has a `webApplicationContext` field.

`springSecurity()` integrates `FilterChainProxy` and test-context post-processors so that `RequestPostProcessor` and `@WithMockUser` are applied properly when using MockMvc. In Spring Boot, `@AutoConfigureMockMvc` with default **filters enabled** usually provides an appropriate `MockMvc` automatically.

**Anti-pattern:**

~~~java
// Easy to create a false positive if you think you already tested security filters:
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new DemoController())
        .build();
~~~

The approach above mainly builds an isolated controller; without adding filter chain/security test support, `/admin` may return `200` even though production requires admin. Similarly, `@AutoConfigureMockMvc(addFilters = false)` disables registering servlet filters into the MockMvc test, so its results cannot be used to claim `SecurityFilterChain` is protected.

Use `@WebMvcTest` when you want a small slice and import the security configuration to test; use `@SpringBootTest` if you want to verify multiple related beans/providers and avoid differences between the test slice and production.

## 6. A runnable Maven Spring Boot 3 + Java 17 project

To avoid examples being mere pseudocode, this section provides **a complete small Servlet application**: form login, two roles, and an endpoint requiring CSRF. It uses Spring Boot `3.5.16` (the specified version baseline for the example, not a claim that it is the latest release) with Boot-managed Security 6.x.

Directory tree:

~~~text
security-mockmvc-demo/
├── pom.xml
└── src/
    ├── main/java/demo/security/
    │   ├── DemoApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/security/
        └── DemoSecurityTests.java
~~~

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-mockmvc-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. `src/main/java/demo/security/DemoApplication.java`

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.3. `src/main/java/demo/security/SecurityConfiguration.java`

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/me", "/settings").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults());
        // CSRF is enabled by default for Servlet web apps; do not disable it.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}demo-pass")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin-pass")
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**`{noop}` is only for demos/tests with fake credentials**, never use it to store production passwords. A real system uses a secure `PasswordEncoder` such as BCrypt/Argon2 per policy, without hard-coding passwords. `hasRole("ADMIN")` compares against authority `ROLE_ADMIN`; `roles("ADMIN")` automatically adds the `ROLE_` prefix. The `/login` endpoints are handled by `formLogin()`; `CSRF` remains at default.

### 6.4. `src/main/java/demo/security/DemoController.java`

~~~java
package demo.security;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/settings")
    public String settings() {
        return "updated";
    }
}
~~~

### 6.5. `src/test/java/demo/security/DemoSecurityTests.java`

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
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
class DemoSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void protectedPageRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginWithCorrectPasswordSucceeds() throws Exception {
        mvc.perform(formLogin()
                    .user("alice")
                    .password("demo-pass"))
                .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void loginWithWrongPasswordFails() throws Exception {
        mvc.perform(formLogin()
                    .user("alice")
                    .password("wrong"))
                .andExpect(unauthenticated());
    }

    @Test
    void mockedUserCanReadOwnName() throws Exception {
        mvc.perform(get("/me")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void nonAdminCannotReadAdminRoute() throws Exception {
        mvc.perform(get("/admin")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminRoute() throws Exception {
        mvc.perform(get("/admin")
                    .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/settings")
                    .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/settings")
                    .with(user("alice").roles("USER"))
                    .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("updated"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void annotationCanSetTestSecurityContext() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
~~~

Run from the directory containing `pom.xml` (with Maven + JDK 17 installed and network access to download dependencies):

~~~bash
mvn test
~~~

**Expected:** 10 tests pass, with no failed/error tests; exact Maven output (elapsed time, reporter name, cache hits) depends on the environment. The verified conditions are:

| Test | What it asserts |
|---|---|
| Public GET | Anonymous receives `200` with body `public`. |
| Protected GET | Anonymous is redirected to the login flow (3xx). |
| Correct form login | Resulting `Authentication` has username `alice`. |
| Wrong form login | No authenticated result. |
| `user()` GET /me | Mock principal appears in the controller. |
| `user()` GET /admin | `ROLE_USER` is denied with `403`. |
| Admin GET | `ROLE_ADMIN` receives `200`. |
| POST missing CSRF | `403` even though the principal is mocked. |
| POST with CSRF | `200` and body `updated`. |
| `@WithMockUser` | Test SecurityContext is injected into the request. |

**Two different test types in the same file:** `formLogin()` actually sends a request into the authentication filter and checks the password against `UserDetailsService`; the `user()`/`@WithMockUser` tests **skip password verification** and are meant to test access policy boundaries.

Note that default servlet form login redirects when the client requests HTML; if the real application is a REST API using a custom entry point returning JSON `401`, expectations must match the real security chain rather than mechanically copying `3xx`.

## 7. Why `formLogin()` and `user()` cannot replace each other

### `formLogin()`

~~~java
mvc.perform(formLogin()
        .user("alice")
        .password("demo-pass"))
    .andExpect(authenticated());
~~~

`SecurityMockMvcRequestBuilders.formLogin()` builds a request matching default form login and supplies a test CSRF token by design. The test path goes through `UsernamePasswordAuthenticationFilter` and `AuthenticationManager` when the filter chain is applied. Use it to verify right/wrong passwords, disabled/locked flags, login failure handlers, and session authentication behavior.

The endpoint and field parameter names can be changed:

~~~java
// If the application configures loginProcessingUrl("/signin")
// and usernameParameter("email"), passwordParameter("secret"):
mvc.perform(formLogin("/signin")
        .userParameter("email")
        .passwordParam("secret")
        .user("alice@example.test")
        .password("wrong"))
    .andExpect(unauthenticated());
~~~

Parameter method names may vary by version; for the Spring Security 6.x API, verify the builder signature from the corresponding `SecurityMockMvcRequestBuilders` when copying this snippet. This snippet illustrates custom form configuration and **does not apply directly** to the demo app in section 6.

### `user()`

~~~java
mvc.perform(get("/admin")
        .with(user("alice").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

`SecurityMockMvcRequestPostProcessors.user()` creates an authentication already considered valid in the mock request. Use it to ask "if principal X has `ROLE_ADMIN`, how does the rule behave?" It **does not verify** whether account "alice" exists in the DB, whether the password is correct, or whether disabled status is blocked during login.

Do not call the test above proof that `AuthenticationProvider` ran. In real life, an attacker cannot grant themselves `ROLE_ADMIN`; only a test fixture is allowed to do so.

## 8. `@WithMockUser`, `@WithUserDetails`, and custom principals

### `@WithMockUser`

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void userPage() throws Exception {
    mvc.perform(get("/me"))
            .andExpect(status().isOk());
}
~~~

The `org.springframework.security.test.context.support.WithMockUser` annotation sets up the test security context before the test method. It is convenient for multiple tests sharing the same role. `roles={"ADMIN"}` creates authority `ROLE_ADMIN`; `authorities={"SCOPE_orders.read"}` uses the exact authority name without adding a role prefix.

**Do not mix `roles` and `authorities` arbitrarily:** decide whether the policy uses `hasRole` or `hasAuthority`.

### `@WithUserDetails`

When a controller/service depends on a real `UserDetails` rather than a fake username, you can use:

~~~java
@Test
@WithUserDetails("alice")
void loadedPrincipal() throws Exception {
    mvc.perform(get("/me"))
            .andExpect(status().isOk());
}
~~~

Requires a `UserDetailsService` with user `alice` in the test context. The annotation loads the principal from the service, but **does not test a password submitted via a form**. Use it when custom `UserDetails` carries tenant/ID/authorities, while credential login tests still use `formLogin()`.

### Custom principal and `@WithSecurityContext`

If the application uses an `InternalPrincipal` with tenant, user ID, factor proof, or policy version, `@WithMockUser` may create the wrong principal type. Use the `authentication()` request post-processor with an appropriate authentication instance, or create a `@WithSecurityContext(factory=...)` annotation to build a test context with the right principal.

Important: build custom principals from a **trusted test fixture**; do not let the controller/authorization layer read roles from a JSON request body. Even when using mocks, tests must reflect the boundaries enforced by the framework.

## 9. Checking anonymous access, permissions, and login results

Useful result matchers:

~~~java
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;

mvc.perform(formLogin().user("alice").password("demo-pass"))
    .andExpect(authenticated().withUsername("alice"));

mvc.perform(formLogin().user("alice").password("bad"))
    .andExpect(unauthenticated());
~~~

You can check `authenticated().withRoles("USER")`, username, or a predicate on `Authentication` to verify authorities/principal. However, if you only pass `user("admin").roles("ADMIN")` from a fixture and then check `authenticated()`, you are verifying the fixture's mocked state, **not** credential verification.

For anonymous requests:

- Web form login usually redirects to `/login`; you can check `3xx` and the appropriate `Location`.
- APIs using bearer tokens usually return `401 Unauthorized` when the token is missing/invalid.
- An authenticated principal lacking permission usually receives `403 Forbidden`.
- A POST with a cookie-based session but no CSRF token can receive `403` even when the principal is valid.

**HTTP behavior depends on the configured entry point, exception handling, CSRF matcher, and authentication mechanism.** Do not force every endpoint missing a user to return `401` if the application intentionally uses a web redirect.

## 10. Testing CSRF, input errors, and handlers

Spring Security CSRF protects state-changing methods by default in many Servlet web apps. With `MockMvc`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;

mvc.perform(post("/settings")
        .with(user("alice"))
        .with(csrf()))
    .andExpect(status().isOk());

mvc.perform(post("/settings")
        .with(user("alice"))
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
~~~

`csrf()` provides a matching token for the test; `csrf().asHeader()` can be used to send it via a header. **Do not disable CSRF just because a test lacks a token** if the real application uses cookie/session web auth. Doing so can cause real CSRF vulnerabilities in production.

To test a **failure handler**, try a wrong password via `formLogin()`, check the redirect or JSON error depending on configuration, and verify account status is not leaked. If the handler uses a generic error message, also test a non-existent user with a wrong password to guard against account enumeration.

Test cookies and sessions when there is specific login/logout logic. One authenticated request in `MockMvc` does not mean the HTTP session of subsequent requests is automatically preserved: obtain and reuse `MockHttpSession` or cookies per the test scenario, instead of expecting each `mvc.perform` to behave like a browser maintaining a session.

## 11. Testing OAuth2 Resource Server JWT: `jwt()` is mock authentication

Servlet Spring Security test provides `jwt()`:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mvc.perform(get("/api/orders")
        .with(jwt().jwt(token -> token
                .subject("usr-1042")
                .claim("scope", "orders:read"))))
    .andExpect(status().isOk());
~~~

The snippet above **is only valid when the application's security/endpoint allows the corresponding authority/claims**; it is not part of the form-login mini app in section 6. `jwt()` builds a mock `JwtAuthenticationToken` to pass through the test authorization context without requiring a token encoded/signed by a real IdP.

You can specify authorities directly:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
    .andExpect(status().isOk());
~~~

Import `org.springframework.security.core.authority.SimpleGrantedAuthority` in the Java snippet.

**Very important point:** `jwt()` **skips verification of the real JWT's signature, `iss`, `aud`, and `exp`**. A passing test with `jwt()` does not prove `JwtDecoder` is configured safely. To verify token validation, send a signed bearer token and use an appropriate decoder or stub `JwtDecoder` to return/throw per case, testing negative cases for signature/issuer/audience/expiry. In Spring Security Resource Server, `JwtAuthenticationToken.getPrincipal()` is normally a `Jwt`, not automatically a custom UserDetails.

### JWT role/scopes mapping

By default, Spring Resource Server typically maps scopes into authorities of the form `SCOPE_x`. If the system has a custom converter from `roles`/groups/tenant to internal authorities, tests must ensure **the converter actually runs**. Passing `jwt().authorities(...)` directly can bypass the converter, so test both the converter and the integration path with claims to catch mapping mistakes.

## 12. OAuth2 Login, OIDC, opaque token: what are the helpers for?

Servlet security-test supports:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;

mvc.perform(get("/profile")
        .with(oauth2Login()));

mvc.perform(get("/profile")
        .with(oidcLogin()
                .idToken(token -> token.claim("user_id", "usr-1042"))));

mvc.perform(get("/api/data")
        .with(opaqueToken()
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_data:read"))));
~~~

Each of these helpers **sets the right kind of mock authentication/principal** for controllers expecting `OAuth2User`, `OidcUser`, or opaque `BearerTokenAuthentication`, avoiding having to run an authorization code flow with a real IdP in every unit test.

They **do not prove**:

- That OAuth2 authorization redirect/callback, `state`, `nonce`, and PKCE were tested end-to-end.
- That the ID Token was validated with the right issuer/audience/signature.
- That opaque-token introspection actually returns `active=false` when a token is revoked.
- That principal mapping from external `(iss,sub)` to internal account is correct across all paths.

Test helpers are used to test controller/authorization logic **assuming authentication is already valid**. To test real federation, add tests for OAuth2LoginAuthenticationFilter/OIDC client/IdP simulator or wire a mock server at the boundary intentionally.

## 13. WebFlux: using WebTestClient and SecurityWebFilterChain

In a WebFlux application, the runtime has `SecurityWebFilterChain`, `ServerWebExchange`, and `ReactiveAuthenticationManager`. Do not use MVC's Servlet `HttpSecurity` or `SecurityFilterChain` in place of reactive configuration.

Example WebFlux security config in a separate application with `spring-boot-starter-webflux`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

This is **integration code**: controllers/reactive user stores and an application context must be added. It does not run alongside the MVC mini app from section 6 as another security chain. For a reactive JWT resource server, `oauth2ResourceServer(jwt -> jwt.jwt(...))` or equivalent configuration and the resource server dependency will be needed.

### Configuring WebTestClient security

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@BeforeEach
void setup() {
    client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
}
~~~

`applicationContext` is the Spring `ApplicationContext` of the **WebFlux app**, and `client` is `org.springframework.test.web.reactive.server.WebTestClient`. `springSecurity()` here belongs to `SecurityMockServerConfigurers`, **a different package from Servlet `SecurityMockMvcConfigurers.springSecurity()`**.

If using Spring Boot `@AutoConfigureWebTestClient`, verify that the client is configured with security appropriate for the WebFlux application. With a client bound to a real server, you cannot arbitrarily use mutators that create a mock server exchange on the server side as when bound to the application context.

## 14. Reactive tests with `mockUser()`, `mockJwt()`, `csrf()`

A test class in a **separate WebFlux project** can be written as:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveSecurityTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousCannotAccessAdmin() {
        client.get().uri("/admin")
                .exchange()
                .expectStatus().isUnauthorized();
        // Assumes the app uses an HTTP Basic entry point.
    }

    @Test
    void userWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminRoute() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void csrfCanBeAddedToStateChangingRequest() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/settings")
                .exchange()
                .expectStatus().isOk();
        // Assumes POST /settings exists and the security rule allows USER.
    }
}
~~~

This is an **integration snippet** because the reactive app/controller and user store must exist with matching routes. You must ensure `/settings` has a controller handler and no business validation alters the result. Replace `@SpringBootTest` with an appropriate test context when the project uses functional routes, router functions, or a custom security chain.

Reactive mock JWT:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders:read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Requires importing `SimpleGrantedAuthority` and a matching endpoint. `mockJwt()` creates a `JwtAuthenticationToken` in the server exchange and **does not send a signed JWT to test the decoder**. Reactive WebTestClient also supports `@WithMockUser` annotations when the security test setup supports them, though you must check the test context and lifecycle.

If the WebFlux application uses `httpBasic` and you want to verify a real password, send the corresponding Basic Authorization header/client filter to invoke the reactive authentication manager/user store; **do not use `mockUser()`** because it bypasses credential verification.

## 15. WebTestClient does not mean WebFlux only

Spring Framework can use `WebTestClient` to test:

- **WebFlux bound to a controller/context** without a server.
- **Spring MVC via the `MockMvcWebTestClient` adapter**.
- **A real HTTP server using `bindToServer()`**.

However, `SecurityMockServerConfigurers.mockUser()`, `mockJwt()`, and `csrf()` operate on a **reactive `ServerWebExchange`**. Do not copy them verbatim into an MVC test using `MockMvcWebTestClient` and expect them to configure the servlet SecurityContext the same way. For MVC, use the Servlet request post-processors from `SecurityMockMvcRequestPostProcessors` or test via actual HTTP login/tokens.

**Choose the adapter based on the application under test, not just the client's return value type.** A WebTestClient assertion can verify an HTTP result yet still skip security if the binding lacks the filter chain/web filter chain.

## 16. Testing method security and custom principals

There are two boundaries: HTTP authorization and method-level authorization. Example:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig {}

@Service
class PayrollService {
    @PreAuthorize("hasAuthority('PAYROLL_APPROVE')")
    void approve(String paymentId) {
        // business operation
    }
}
~~~

If you only test `GET /public`, you have not proven `@PreAuthorize` works. You can use:

- `@WithMockUser(authorities="PAYROLL_APPROVE")` to test that the method/service is allowed.
- `@WithMockUser(roles="USER")` to test missing authority and denial.
- A `MockMvc` request hitting a real controller to verify proxy/method-security interception and mapped HTTP status.
- Unit/service integration for role-tenant/resource constraints, along with negative tests to prevent bypasses.

**Beware of self-invocation:** calling a method annotated with `@PreAuthorize` from within the same bean can bypass the Spring proxy. A test that invokes the method directly via `new PayrollService()` also does not trigger method security. Tests must obtain the bean from the Spring context or go through an HTTP request with a real security chain.

If an internal principal carries tenant/owner/factor proof, `@WithMockUser` may lack metadata; use `@WithSecurityContext` or `authentication()` with the proper internal principal, then test cross-tenant, disabled-account, and step-up freshness cases. Do not accept self-declared role/tenant fields in a request body in place of authentication data.

## 17. Testing stateful sessions, logout, and no privilege leakage

Many tests impersonate a user with `with(user("alice"))` on **an isolated request**, so they do not prove the session persists across two requests.

For stateful form login, test:

1. Send `POST /login` with valid CSRF and correct credentials.
2. Capture `MockHttpSession` or cookies from the response per configuration.
3. Send a follow-up request using that exact session/cookie.
4. Verify the protected endpoint allows access.
5. Send logout via the `logout()` helper or a real logout request with CSRF.
6. Resend the old session/cookie and ensure it is no longer accepted.

Spring Security test provides `SecurityMockMvcRequestBuilders.logout()`; the helper's default logout URI and CSRF depend on setup. Be careful not to only check the `/login?logout` redirect while forgetting to verify server-side session invalidation.

If the app uses Spring Session Redis/JDBC, a test with a single MockMvc context may not prove revocation across all nodes. Integration tests with a real store and multiple app instances, or verification of repository semantics, are needed.

## 18. Testing negative cases before trusting a green build

A login suite should include at least:

| Scenario | Expectation |
|---|---|
| Anonymous GET public | Allowed when policy is public. |
| Anonymous GET protected web page | Redirect to login; or 401 if API entry point. |
| Anonymous POST protected | Blocked by CSRF/authentication per policy, with no side effects. |
| Correct username/password | Authenticated result, correct principal and session behavior. |
| Wrong password | Not authenticated, generic failure response. |
| Non-existent username | Does not leak account existence via status/body/obvious timing. |
| Account disabled/locked | Login disallowed; appropriate recovery policy. |
| `@WithMockUser` role USER calling admin route | 403. |
| ADMIN user calling admin route | 200/expected behavior. |
| Missing CSRF on session-backed POST | 403 if CSRF required. |
| Invalid CSRF token | 403. |
| Valid CSRF token | Can be processed according to authorization. |
| Mocked JWT missing scope | 403 when endpoint requires the authority. |
| Real JWT with wrong signature/issuer/audience/expired | Token decoder rejects; cannot be proven with `jwt()` alone. |
| OIDC mock principal missing required claim | Denied per mapping/policy. |
| Valid token but disabled owner | Denied if online account-state policy requires it. |
| Cross-tenant principal | Cannot access another tenant's resources. |
| Incomplete MFA | Must not be elevated to high-privilege fully authenticated actions. |
| Logout | Old session/cookie no longer grants access. |
| CSRF/headers disabled in test | Suite must detect the difference instead of passing silently. |
| Authentication backend down | Fail closed; never default to login success. |

**Do not check only 200/401/403**: assert principal/role, response body, cookies, headers, service/repository side effects, session handling, and events/audits (if required). A request returning 403 due to CSRF does not prove the role rule blocked it — provide a valid CSRF token when testing authorization on a POST.

## 19. Common pitfalls and causes

### Pitfall 1: forgetting to integrate the security filter chain

`MockMvcBuilders.standaloneSetup(...)` or `@AutoConfigureMockMvc(addFilters=false)` can make an endpoint return 200 when production returns 403. **Fix:** configure `springSecurity()`/`@AutoConfigureMockMvc` properly and include negative tests for anonymous/roles.

### Pitfall 2: using `@WithMockUser` to claim password login works

A mock user creates a pre-built authentication without checking the password encoder/user repo/provider. **Fix:** also test `formLogin()` or the actual HTTP Basic/bearer credential path.

### Pitfall 3: missing `csrf()` and assuming a role was denied

A POST without CSRF fails with 403 before the authorization rule is even tested. **Fix:** when testing POST permissions, supply valid CSRF; when testing CSRF itself, test missing/invalid tokens separately.

### Pitfall 4: `roles("ROLE_ADMIN")`

`roles("ADMIN")` automatically generates `ROLE_ADMIN`. Using `roles("ROLE_ADMIN")` can create the wrong authority or be rejected because the prefix is already present. **Fix:** for roles, pass `"ADMIN"`; for literal authorities, use `authorities("ROLE_ADMIN")` when the API supports it.

### Pitfall 5: `jwt()` test is green but production JWT verifier is broken

Mock JWT does not verify signature/issuer/audience/expiry. **Fix:** test the converter and decoder separately, with integration tests using signed JWTs or a decoder mocked for negative scenarios.

### Pitfall 6: testing Servlet helpers in a reactive context

`SecurityMockMvcRequestPostProcessors.user()` and `SecurityMockServerConfigurers.mockUser()` target different runtimes. **Fix:** branch tests by Spring MVC vs. WebFlux using the right package.

### Pitfall 7: testing only happy-path roles

No negative tests for anonymous, USER calling ADMIN, wrong password, expired token, or CSRF. **Fix:** test an allow/deny matrix with emphasis on fail-closed behavior.

### Pitfall 8: mocking away the entire security configuration

If `@WebMvcTest` mocks out the filter/proxy too, the test does not prove production policy. **Fix:** import the real filter chain when that is what needs testing; use `@SpringBootTest` when multiple integration beans are involved.

### Pitfall 9: test context accidentally pointing to production

Never use production accounts, real IdPs, or real signing keys for integration tests. Use profiles/test datasources/local IdP fixtures, and avoid logging test credentials if there is any risk of mixing with production.

### Pitfall 10: results differ only because of request matching

A security matcher `/api/**` may fail to cover a new endpoint; `permitAll`/`anyRequest`/multiple filter chains have different ordering. **Fix:** test every sensitive route directly and match against the real chain, not just service methods.

## 20. Maintainable test suite structure

A codebase should generally layer its tests clearly:

~~~text
src/test/java/
  security/
    PasswordLoginMockMvcTests.java
    RoleAuthorizationMockMvcTests.java
    CsrfMockMvcTests.java
    SessionAndLogoutTests.java
    JwtClaimMappingTests.java
    JwtDecoderIntegrationTests.java
    OidcPrincipalMappingTests.java
    SecurityEventTests.java
  reactive/
    ReactiveSecurityWebTestClientTests.java (only if WebFlux project)
~~~

You can use custom fixtures `aliceUser()`, `adminJwt()`, `oidcTenantUser()`, but name them to make clear they are **mocked security contexts**. Do not make a default request always run as admin across the entire suite: it can mask an endpoint that should have blocked anonymous access.

Recommendations:

- Name tests after behavior, e.g., `anonymousShouldNotApprovePayment`, `validPasswordShouldAuthenticate`.
- Use JUnit parameterized tests when testing a matrix of multiple roles/scopes/tenants.
- Keep fixtures minimal and independent of test execution order; reset session/state between tests.
- Use controllable time for JWT expiry/MFA freshness, never `Thread.sleep()`.
- Keep negative tests across every change to SecurityFilterChain, request matchers, JWT converters, or resource permissions.
- Test security at the controller/service level and in system integration when Redis/IdP/LDAP/KMS are involved, without letting mocks hide trust boundaries.
- In CI, security test failures must fail the build; never disable filters, CSRF, or assertions just to make it pass.

## 21. Checklist before marking complete

- [ ] Project is identified as Servlet MVC or reactive WebFlux; the right test tool is used.
- [ ] `spring-security-test` is added in test scope with a version compatible with runtime Spring Security.
- [ ] `MockMvc` has Spring Security filters via `springSecurity()` or Boot auto-config; `addFilters=false` is not used when testing policy.
- [ ] WebFlux `WebTestClient` has `apply(springSecurity())` and proper server context setup.
- [ ] Tests cover the actual login credential path (`formLogin()`/HTTP Basic/OIDC callback integration) separately from mocked principal paths.
- [ ] Tests cover anonymous, wrong password, disabled/locked user, and role/authority allow/deny.
- [ ] Tests cover POST with valid/invalid/missing CSRF matching the real application.
- [ ] Tests cover JWT/OIDC/OAuth2 principals via helpers and real validation via additional integration tests.
- [ ] Tests check tenant/resource-level permissions rather than roles alone.
- [ ] Tests cover session/logout without assuming session continuity from a mocked test user.
- [ ] Tests cover method security through a Spring-managed proxy, avoiding self-invocation false positives.
- [ ] No secrets, tokens, or user PII are placed in logs/test artifacts.
- [ ] Negative/security regression tests run automatically in CI.
- [ ] The test suite uses mocks explicitly and never claims a mock bypassing the decoder/provider verifies production auth.

## 22. Summary

`spring-security-test` helps test the **right boundaries** of Spring Security when combined with HTTP test infrastructure:

- For **Spring MVC/Servlet**, use `MockMvc` and `springSecurity()` or `@AutoConfigureMockMvc` with filters. `formLogin()` goes through the authentication mechanism; `user()`/`@WithMockUser` mock authentication to focus on testing authorization.
- For **Spring WebFlux**, use `WebTestClient` + reactive `springSecurity()` together with `mockUser()`, `mockJwt()`, and `csrf()`; reactive helpers cannot be swapped arbitrarily with servlet helpers.
- For **JWT/OIDC**, mocking principals/claims is convenient but **does not replace** testing signatures, issuer, audience, expiry, callbacks, nonce, state, PKCE, and account mapping at system boundaries.

A trustworthy test suite needs both **positive and negative cases**, tests the real security chain, understands which helpers bypass credential verification, and prevents CSRF/roles/sessions from becoming false positives.

## References

- [Spring Security 6.5 — MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `springSecurity()`, security filter chain, and test context.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user()` and `@WithMockUser`.
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, invalid token, and header token.
- [Spring Security — MockMvc Result Matchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html): `authenticated()` and `unauthenticated()`.
- [Spring Security — OAuth2/OIDC/JWT MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oauth2Login()`, `oidcLogin()`, `jwt()`, and `opaqueToken()`.
- [Spring Security 6.5 — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `WebTestClient.apply(springSecurity())`.
- [Spring Security 6.5 — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser()` and reactive `@WithMockUser`.
- [Spring Security — Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): reactive `csrf()`.
- [Spring Security — Reactive OAuth2/JWT Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` and related helpers.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-context, controllers, MockMvc adapter, and HTTP server.
- [Spring Boot 3.5.16 Release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/): Maven demo version.
