# Roles of the core, web, config, crypto, and test Libraries in Spring Security

When initializing a Spring Security project, you may see artifacts such as `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-crypto`, and `spring-security-test` in the dependency tree. They belong to the same ecosystem but carry **different responsibilities**: providing identity and authority models, protecting web requests, declaring policies, handling necessary cryptography, and supporting testing.

Understanding each library's role helps you know where to import classes from, explain why `spring-boot-starter-security` is usually enough for a basic web application, spot missing dependencies, and test the exact security aspect you intend to verify. This lesson uses **Spring Boot 3 + Spring Security 6, Java 17+, and a Servlet/Spring MVC application** as its context. For other Spring Boot/Spring Security versions, consult the matching documentation and let the BOM/dependency management select compatible versions.

## 1. Big Picture: Five Modules, Five Responsibility Groups

| Artifact | Primary Role | Example Classes / APIs | Where Is It Typically Used? |
| --- | --- | --- | --- |
| **`spring-security-core`** | Foundational abstractions for authentication, security context, authorities, authorization | `Authentication`, `SecurityContextHolder`, `GrantedAuthority`, `UserDetails`, `AuthenticationManager`, `AuthorizationManager` | Application-layer authentication/authorization logic and integration modules |
| **`spring-security-web`** | Integrates security with web requests/responses, primarily via filter chains in Servlet apps | `SecurityFilterChain`, `FilterChainProxy`, `BasicAuthenticationFilter`, `CsrfFilter`, `AuthorizationFilter` | Web/API request processing |
| **`spring-security-config`** | Declares, assembles, and configures security policies | `HttpSecurity`, `@EnableWebSecurity`, `@EnableMethodSecurity`, `authorizeHttpRequests`, `httpBasic` | `@Configuration` classes and the security DSL |
| **`spring-security-crypto`** | Primitives/helpers for symmetric encryption, key generation, and **one-way password hashing** | `PasswordEncoder`, `BCryptPasswordEncoder`, `PasswordEncoderFactories`, `Encryptors`, `KeyGenerators` | Password storage, cryptographic utilities as needed |
| **`spring-security-test`** | Creates mock security contexts, MockMvc integration, and utilities for testing authorized/unauthorized requests | `@WithMockUser`, `user()`, `httpBasic()`, `csrf()`, `springSecurity()` | `src/test`, test classpath |

These five modules are **not five stages that always execute sequentially**. `core` defines shared contracts and objects; `web` handles the HTTP boundary; `config` creates configurations and wires components; `crypto` provides tools for protecting secrets, especially passwords; `test` helps verify behavior in tests, not as an automatic runtime protection layer.

A helpful mental model:

```text
                 +----------------------+
                 | spring-security-test |
                 |  test security flow  |
                 +-----------+----------+
                             | supports testing
                             v
  +----------------------- WEB APPLICATION -------------------+
  |                                                           |
  |  spring-security-config           spring-security-web     |
  |  HttpSecurity / policy    --->    SecurityFilterChain     |
  |                                   FilterChainProxy        |
  |                                   Authentication filters  |
  |                                          |                |
  |                                          v                |
  |                              spring-security-core         |
  |                              Authentication / Context     |
  |                              GrantedAuthority / authz     |
  |                                          ^                |
  |                                          |                |
  |                              spring-security-crypto       |
  |                              PasswordEncoder, hashing     |
  +-----------------------------------------------------------+
```

The arrows show **conceptual responsibility relationships**, not an exact Maven dependency list. To know which JAR contains a class, inspect its package/JAR; to see actual dependencies, check your project's `runtimeClasspath` and `testRuntimeClasspath`.

## 2. spring-security-core: The Common Language of Authentication and Authorization

`spring-security-core` provides core interfaces and implementations usable across many application types rather than being tightly coupled to HTTP Servlets.

Typical concepts:

- **`Authentication`** represents an authentication request or result, holding `principal`, `credentials`, `authorities`, and the `authenticated` state.
- **`AuthenticationManager`** and **`AuthenticationProvider`** coordinate/implement identity verification via the appropriate mechanism.
- **`SecurityContext`** stores the `Authentication` for the current processing context; **`SecurityContextHolder`** is the API for accessing that context.
- **`GrantedAuthority`** describes a granted permission, typically as a role/permission/scope; **`SimpleGrantedAuthority`** holds a concrete authority string.
- **`UserDetails`**, **`UserDetailsService`**, and related classes describe users in username/password flows.
- **`AuthorizationManager`** is the abstraction for making access decisions from an `Authentication` and a protected context.

Example imports from the core group:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.authorization.AuthorizationManager;
```

A snippet reading the identity/authorities already present in the context:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String principalName = authentication.getName();
    boolean hasAdmin = authentication.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
}
```

This is an **illustrative snippet inside a Spring Security application**, not a standalone Java program. For anonymous requests, `authentication` may be null or an anonymous token; `isAuthenticated()` on an anonymous token can return true. To protect endpoints, use Spring Security's `authenticated()` rule and required authority policies rather than relying solely on `authentication != null` or `isAuthenticated()`.

**Limits of core:** these abstractions **do not automatically block HTTP requests** unless properly integrated into the security filter chain or corresponding invocation mechanism. Even a manually constructed `Authentication` object marked `authenticated=true` does not mean credentials were verified.

## 3. spring-security-web: Applying Security to HTTP Requests

In the Servlet model, request protection is primarily carried out through filters. Notable classes:

- **`FilterChainProxy`** is the central component that selects the `SecurityFilterChain` matching a request.
- **`SecurityFilterChain`** holds the list of filters and matcher for a group of requests.
- **`BasicAuthenticationFilter`** handles HTTP Basic authentication when enabled.
- **`UsernamePasswordAuthenticationFilter`** supports form login as configured.
- **`CsrfFilter`** validates the CSRF token on protected requests.
- **`AuthorizationFilter`** enforces the assembled authorization policies.
- **`ExceptionTranslationFilter`** handles authentication/authorization exceptions in the web layer.

These classes generally live under `org.springframework.security.web...`. Spring Boot integrates filters with the Servlet container via the appropriate registration mechanism; when using the starter and standard configuration, you usually **do not register each filter manually**.

Conceptual flow:

```text
Client HTTP request
        |
        v
Servlet filter chain
        |
        v
DelegatingFilterProxy
        |
        v
FilterChainProxy  (spring-security-web)
        |
        v
Matching SecurityFilterChain
        |
        +-- Security filters: context, CSRF, authentication, authz ...
        |
        v
DispatcherServlet -> Controller -> Service
```

**Do not treat the steps in the diagram as a fixed order for every filter.** The actual order varies by mechanism, matchers, and configuration, and a filter can reject a request before the controller is ever invoked.

### 3.1. SecurityFilterChain vs. HttpSecurity

- `SecurityFilterChain` is an abstraction in **`spring-security-web`** describing the filter chain selected for a request.
- `HttpSecurity` is a **builder in `spring-security-config`** used to declare and construct a `SecurityFilterChain`.

For example, you write:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

`HttpSecurity` helps *configure*, whereas the resulting `SecurityFilterChain` after `build()` is *used to protect requests*. The snippet above is a fragment of a `@Configuration` class and requires imports/dependencies plus a way to supply authenticated users.

### 3.2. Multiple Chains and Request Leakage Mistakes

An application can declare multiple `SecurityFilterChain` beans, each with its own `securityMatcher` and priority order. `FilterChainProxy` picks the **first matching chain**; remaining chains do not automatically apply to the same request. If no chain matches, the request may bypass Spring Security protection.

Therefore, when separating `/api/**` and `/admin/**`, verify precedence and ensure a fallback chain exists. For a simple application, using one chain with `anyRequest().denyAll()` for undeclared endpoints keeps the policy explicit.

## 4. spring-security-config: Declaring and Wiring Policies

`spring-security-config` provides the API to declare security via Java configuration (and other supported configuration styles). Here you commonly encounter:

- **`HttpSecurity`**: builder for declaring HTTP security.
- **`@EnableWebSecurity`**: enables web security configuration in a Spring application when needed.
- **`@EnableMethodSecurity`**: enables method-level protection with `@PreAuthorize`, `@PostAuthorize`, etc., as configured.
- **`authorizeHttpRequests`**, **`requestMatchers`**, **`httpBasic`**, **`formLogin`**, **`csrf`**, **`sessionManagement`**, and other DSLs.

Example:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This is a configuration fragment (missing imports and application class), not a standalone Java file. Rules inside `authorizeHttpRequests` are evaluated in order, so narrower matchers should come before `anyRequest()`. `hasRole("ADMIN")` requires the authority `ROLE_ADMIN` by default; `hasAuthority("ADMIN")` matches the exact string `ADMIN`.

### 4.1. The config Module Does Not Replace core or web

`spring-security-config` helps create beans, policies, and chains; it does not itself become an HTTP filter processing requests. Authorities and identities still use abstractions from `core`, while the executing filters in Servlet apps generally come from `web`.

Also distinguish **Spring Boot auto-configuration** from `spring-security-config`. Boot has its own auto-configuration, starters, and dependency management; `spring-security-config` is the Spring Security module providing security configuration tools. They collaborate rather than being a single artifact.

### 4.2. Why You Should Not Copy Legacy Configurations

With Spring Security 6, `WebSecurityConfigurerAdapter` is no longer the configuration API in use. The modern pattern is declaring a `SecurityFilterChain` bean along with required security beans. Spring Boot 3 uses the **`jakarta.servlet`** namespace instead of legacy `javax.servlet` imports.

When reading documentation across versions, match the corresponding APIs rather than mixing Spring Security 5, 6, and 7 code. If `HttpSecurity` or `@EnableMethodSecurity` cannot be resolved, check the `spring-security-config` dependency, version, and imports—do not manually add a JAR of a different version to the classpath.

## 5. spring-security-crypto: Password Encoding, Key Generation, and Encryption

`spring-security-crypto` contains Spring Security's cryptographic utilities. Common needs include:

| Feature Group | Example APIs | Purpose |
| --- | --- | --- |
| Password hashing | `PasswordEncoder`, `BCryptPasswordEncoder` | Store and verify passwords via salted hashes rather than plaintext |
| Hash compatibility/upgrade | `DelegatingPasswordEncoder`, `PasswordEncoderFactories` | Identify algorithms via prefixes such as `{bcrypt}` and support migration |
| Key/salt generation | `KeyGenerators` | Generate values for appropriate cryptographic mechanisms |
| Symmetric data encryption | `Encryptors`, `BytesEncryptor`, `TextEncryptor` | Encrypt data that must be decrypted later, when the use case and key management are sound |

**Password encoding differs from encryption:**

- Passwords should use **one-way hashing** with a salt and a proper password-hashing algorithm. At login, verify with `PasswordEncoder.matches(rawPassword, storedHash)`.
- Data that must be recovered in original form—such as a secret that must be forwarded to another system—may require **two-way encryption** alongside key management, access control, and lifecycle handling; do not use password hashing for that problem.
- Never use Base64, plain SHA-256, or symmetric encryption in place of dedicated password hashing when storing passwords.

Example:

```java
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder =
    PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode("demo-password");
boolean right = encoder.matches("demo-password", storedHash);
boolean wrong = encoder.matches("wrong-password", storedHash);
```

This snippet requires the appropriate Spring Security dependency. `right` evaluates to `true`, `wrong` to `false`; the hash value is **not deterministic** because it includes a salt. `DelegatingPasswordEncoder` stores an algorithm-identifying prefix inside the hash, such as `{bcrypt}...`.

**Do not compare two `encode` outputs with `equals`:** use `matches`. Never hardcode real passwords, log plaintext passwords/hashes, or store fixed hashes copied from demo documentation in production.

### 5.1. Crypto Does Not Perform Authentication or Authorization on Its Own

`spring-security-crypto` can be used standalone to encode/check passwords, yet by itself it does not know:

- Which user is attempting to log in;
- Whether the account is locked or disabled;
- Which authorities the principal should receive;
- Which endpoints or objects are permitted;
- Which CSRF, session, or filter chain setup is active.

Those responsibilities belong to providers, policies, the web layer, and business logic. `PasswordEncoder` is one component **of the password authentication process**, not a complete security solution.

## 6. spring-security-test: Verifying Security Behavior in Tests

`spring-security-test` is a library **intended for test scope**. Common tools:

| Tool | Purpose | Checks Real Passwords? |
| --- | --- | --- |
| `@WithMockUser` | Places a mock user into the SecurityContext during test execution | No |
| `with(user("alice"))` | Attaches a mock user/authorities to a MockMvc request | No |
| `with(httpBasic("alice", "password"))` | Adds a Basic header to the request so it passes through the configured auth filter | Can verify through the real provider in integration tests |
| `with(csrf())` | Adds a valid CSRF token to a MockMvc request | Not user authentication |
| `with(csrf().useInvalidToken())` | Simulates an invalid CSRF case | No |
| `springSecurity()` | Integrates Spring Security with a manually built MockMvc | Test setup, not an auth provider |
| `@WithAnonymousUser` | Runs the test with an anonymous identity | No |

Example:

```java
mvc.perform(get("/admin")
        .with(user("reader").roles("USER")))
    .andExpect(status().isForbidden());

mvc.perform(post("/notes")
        .with(user("reader").roles("USER"))
        .with(csrf()))
    .andExpect(status().isOk());
```

These calls **assume** the application has matching controllers and rules, MockMvc is integrated with Spring Security, the corresponding static imports are present, and `POST /notes` actually permits writes. `user()` creates a mock user context; it verifies **authorization for the given authorities**, not whether `UserDetailsService` and `PasswordEncoder` authenticate passwords correctly.

### 6.1. Authentication Tests and Authorization Tests Must Be Intentional

- Use `httpBasic()`, form login tests, or a proper token verifier when you want to exercise the **real authentication** mechanism.
- Use `@WithMockUser`/`user()` when you want to isolate and test **authorization/policy** with preset authorities.
- Use `csrf()` or an invalid token when testing **CSRF protection** in a Servlet app with CSRF enabled.
- Test anonymous access, authorized accounts, under-privileged accounts, missing CSRF tokens, and valid CSRF tokens.
- For sensitive operations, do not assert only the HTTP status—also verify that the database or mocked service **receives no side effects** when rejected.

### 6.2. Does the Test JAR Protect Production?

No. `spring-security-test` helps write and run tests; it does not add production protection filters and must not be used as a source for runtime code. Keep the dependency in `testImplementation` (Gradle) or `test` scope (Maven).

## 7. Initializing Dependencies in Spring Boot

### 7.1. Recommended Approach with Spring Boot 3

For Spring MVC, create a Java 17+ compatible Spring Boot 3 project via Spring Initializr or a valid Boot template. In `build.gradle` (Groovy DSL) with the Boot Gradle plugin applied, you usually only need:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-boot-starter-security` bundles the security dependencies needed for typical use cases (notably config and web, while core/crypto abstractions are pulled in transitively). `spring-boot-starter-web` provides Spring MVC/Servlet for the example app. `spring-boot-starter-test` includes JUnit 5, Spring Test, and Boot test utilities; `spring-security-test` adds security testing helpers.

Because Spring Boot manages versions via its BOM/plugin, **do not add independent version numbers** to `spring-security-web`, `config`, or `test` just to "pick a newer one." What matters is that Spring Security modules stay compatible with one another and with the running Boot version.

If using Maven in a Boot project with dependency management configured:

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

This is only the **dependencies section**, not a complete `pom.xml`. When using Maven without the Boot BOM, you need dependency management or explicitly verified compatible versions.

### 7.2. Do You Need to Declare All Five Modules Manually?

**Usually no** when using the Spring Boot starter. Adding all five modules manually can create duplicate dependencies, complicate version management, and invite scope mistakes.

If **not using Spring Boot** and integrating Spring Security Servlet yourself, the direct starting points are typically `spring-security-web` and `spring-security-config`, along with a build/BOM mechanism for versions and extra dependencies per use case. `core`/`crypto` can arrive transitively. `spring-security-test` must be declared separately when writing tests. That is why advice like "just add all five JARs" does not reflect how Spring Security is properly consumed.

### 7.3. Reading the Actual Dependency Tree

In a Gradle project:

```bash
# Runtime dependencies: which modules load when running the app
./gradlew dependencies --configuration runtimeClasspath

# Test dependencies: what is included when running tests
./gradlew dependencies --configuration testRuntimeClasspath

# Who pulls in core, and which version is selected?
./gradlew dependencyInsight \
  --dependency spring-security-core \
  --configuration runtimeClasspath

# Run tests
./gradlew test
```

On Windows PowerShell, use `.\gradlew.bat` instead of `./gradlew` and write each command on a single line (removing Bash's `\` line continuation). With Maven, use `mvn dependency:tree` to inspect versions and transitive relationships.

Note: the actual dependency tree depends on Boot/Security versions, other starters, and version resolution rules. The table/modules in this lesson describe **responsibilities**, not a substitute for checking Gradle/Maven output.

## 8. Complete Example: From Modules to Protected HTTP Requests

This example set uses **Spring Boot 3 / Java 17+**, Spring MVC, two in-memory users, and HTTP Basic. All files belong to package `demo.security` and can be placed in a Boot 3 project with the dependencies from section 7.

The goal is to see each layer clearly:

- **core:** `UserDetailsService`, `Authentication`, and user authorities.
- **crypto:** `PasswordEncoderFactories` and `PasswordEncoder` hashing passwords.
- **config:** `HttpSecurity` and matchers defining the security policy.
- **web:** `SecurityFilterChain` and security filters processing requests.
- **test:** MockMvc simulating requests and asserting 200/401/403/CSRF.

### 8.1. Creating the Application

Create `src/main/java/demo/security/SecurityModulesDemoApplication.java`:

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityModulesDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityModulesDemoApplication.class, args);
    }
}
```

Create `src/main/java/demo/security/SecurityConfig.java`:

```java
package demo.security;

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

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/me", "/notes").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Explanation:

1. `users()` creates two `UserDetails` instances with demo data; passwords are passed through `PasswordEncoder`. `DelegatingPasswordEncoder` prefixes the algorithm identifier such as `{bcrypt}`.
2. `HttpSecurity` is the **config** builder; the resulting `SecurityFilterChain` is a **web** type.
3. `.hasRole("ADMIN")` checks `ROLE_ADMIN` by default convention; `.roles("ADMIN")` on user creation supplies that corresponding authority.
4. `httpBasic` enables Basic header verification using the appropriate authentication components; `csrf` preserves request protection when CSRF applies.
5. `anyRequest().denyAll()` denies endpoints without an explicit rule, avoiding accidentally exposing new routes.
6. The passwords are for local testing only. Production requires HTTPS, proper identity storage, and secrets handled per deployment standards.

Create `src/main/java/demo/security/DemoController.java`:

```java
package demo.security;

import org.springframework.security.core.Authentication;
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
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping("/notes")
    public String addNote() {
        return "created";
    }
}
```

`Authentication` in the controller is populated from the security context; it is a **core** abstraction. In real applications, do not return raw `Authentication` objects or credentials to clients. `POST /notes` only demonstrates authorization and CSRF ordering; it does not persist to a database.

### 8.2. Verifying with Tests Running Under Spring Boot

Create `src/test/java/demo/security/SecurityIntegrationTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

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

@SpringBootTest
@AutoConfigureMockMvc
class SecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void privateEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void httpBasicAuthenticatesReader() throws Exception {
        mvc.perform(get("/me").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void adminRoleIsRequired() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void csrfIsRequiredForPost() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }
}
```

**Note on imports above:** the static imports are wrapped before the dot for readability; in Java, continuing a qualified name across a line break before a dot is syntactically valid. If your IDE applies a formatter, each `import static` can be placed on a single line. The test file requires Spring Boot test and `spring-security-test` on the test classpath, and MockMvc is automatically configured with Spring Security by `@AutoConfigureMockMvc`.

Run:

```bash
./gradlew test --tests demo.security.SecurityIntegrationTest
```

On Windows:

```powershell
.\gradlew.bat test --tests demo.security.SecurityIntegrationTest
```

**Expected result:** all **5 test methods** pass in a properly configured project. No fixed Gradle stdout string is shown because task counts, logs, and tool versions can vary. HTTP statuses are verified by assertions inside the test itself.

### 8.3. Reviewing the Results Through the Module Lens

| Simulated Request | Expected | Primary Contributing Modules |
| --- | --- | --- |
| GET `/public` without login | 200 | `config` declares `permitAll`; `web` runs the filter chain |
| GET `/me` without login | 401 | `web` issues the Basic challenge; `core` defines identity abstractions |
| GET `/me` with valid Basic | 200 | `web` reads header; `core` authenticates; `crypto` verifies hash |
| GET `/admin` as reader | 403 | `config` declares role rule; `core` provides authorities; `web` rejects request |
| GET `/admin` as admin | 200 | The components above collaborate |
| POST `/notes` without CSRF token | 403 | `web` enforces CSRF protection |
| POST `/notes` with valid CSRF token | 200 | `test` supplies simulated CSRF token; `web` validates request |

An HTTP 403 alone does not prove "missing role", because a request can also be blocked by CSRF. When debugging, identify the exact filter or policy that rejected it.

### 8.4. Distinguishing Real Authentication Tests from @WithMockUser

`@WithMockUser` or `with(user(...))` **simulates** authentication in tests, which is suitable when you only want to test policies. With `httpBasic("reader","reader-pass")` as in the example, the request passes through HTTP Basic and authenticates against the application's user store/`PasswordEncoder`, testing the multi-module flow together.

A passing test with `@WithMockUser(roles = "ADMIN")` does not prove that a password in the database can log in, or that a real OAuth2 token is verified properly. Choose the test style based on what you want to prove.

## 9. Extending Further: Adding Modules Beyond These Five

The five main modules cover the foundation, while specialized use cases may require:

| Use Case | Typical Module/Starter | Notes |
| --- | --- | --- |
| API using OAuth2 Bearer JWT | `spring-boot-starter-oauth2-resource-server`, matching OAuth2 Resource Server/Jose modules | Verify signature, issuer, audience, expiration, and scopes; do not build an incomplete custom JWT verifier |
| App logging in via OAuth2/OIDC | `spring-boot-starter-oauth2-client` | Distinguish OAuth2 client/OIDC login from resource server |
| Spring LDAP authentication | LDAP integration module when needed | Configure directory, connection, and authority mapping appropriately |
| Method security | `@EnableMethodSecurity` from config + core mechanisms | Method security must actually be enabled and invoked across the proper proxy boundary |
| Reactive WebFlux application | Corresponding reactive security configuration/architecture | Do not copy Servlet filters and MockMvc directly to WebFlux; refer to `WebTestClient`/WebFlux security |

Do not assume all of the dependencies above are included in `spring-boot-starter-security`. Add the exact modules matching your application type and needs while keeping versions aligned via the BOM.

## 10. Distinguishing Module Errors from Configuration or Policy Errors

| Symptom | Likely Cause | Proper Check |
| --- | --- | --- |
| `Cannot resolve HttpSecurity` | Missing `spring-security-config`, wrong import, or version mismatch | Check starter, imports, and runtime dependency tree |
| `Cannot resolve SecurityFilterChain` | Missing `spring-security-web` or dependency absent from current module | Check starter/build configuration |
| `Cannot resolve PasswordEncoder` | Missing `spring-security-crypto` or wrong import | Check `org.springframework.security.crypto.password.PasswordEncoder` |
| `Cannot resolve @WithMockUser` | `spring-security-test` not added to test classpath | Check `testImplementation` and imports |
| `NoClassDefFoundError` at runtime | JAR missing at runtime, version conflict, or excluded dependency | Inspect `runtimeClasspath` / `dependencyInsight` |
| Private GET returns 401 | Unauthenticated or missing credentials | Check filters, Basic/form/token mechanism, user store, security logs |
| Logged-in user gets 403 on admin GET | Missing authority or policy denial | Compare `ROLE_ADMIN` vs `hasRole("ADMIN")`; check object permissions |
| MockMvc POST returns 403 | Possibly missing or invalid CSRF token | Check `csrf()` and the authentication mechanism in use |
| An endpoint is accidentally public | Missing or misordered chain/matcher | Check `securityMatcher`, `@Order`, `anyRequest`, and anonymous tests |
| Tests pass but production returns 401 | Tests used `@WithMockUser` and bypassed real authentication | Add integration tests exercising real `httpBasic`/token verification |

**Do not rush to add dependencies to fix every 403.** If the project compiles and Spring Security is running yet denies access, the cause likely lies in matchers, authorities, CSRF, or business policies—not a missing JAR.

## 11. Common Misconceptions

1. **Treating core as sufficient to protect HTTP.** Core provides abstractions; protecting Servlet requests requires web filters and policies.
2. **Treating web as the place where all policies live.** Web receives/responds to requests, while `HttpSecurity` and configuration annotations come from config; business-object permissions still belong in services/repositories.
3. **Treating config as Boot auto-configuration.** They are two collaborating mechanisms. Boot starters assemble dependencies and defaults; the config module provides the DSL.
4. **Assuming crypto performs login on its own.** `PasswordEncoder.matches` is only one step of authentication; it does not load users, evaluate roles, or protect routes.
5. **Assuming the test module should run in production.** `spring-security-test` belongs to test scope and does not replace real filters.
6. **Using `@WithMockUser` to conclude password login works.** Mock users bypass the password provider. Use real authentication integration tests when verifying login.
7. **Adding modules with differing versions.** Easily causes `NoSuchMethodError` or classpath conflicts. Use the Boot/Spring Security BOM.
8. **Copying legacy `WebSecurityConfigurerAdapter` config into Boot 3.** The modern API uses `SecurityFilterChain` beans.
9. **Assuming `permitAll()` bypasses every filter.** The request still traverses the matched chain; for example, a POST may still be blocked by CSRF.
10. **Assuming roles alone protect every object.** Correct authentication and authorities do not replace owner/tenant/record-level policies.
11. **Disabling CSRF just to make tests pass.** For cookie/session applications, that can introduce a vulnerability; use `csrf()` in tests and evaluate your API's threat model properly.
12. **Inferring dependencies solely from package names.** A module may use classes from another module via transitive dependencies; always verify the artifact/JAR and dependency tree.
13. **Ignoring the reactive stack.** Spring WebFlux is configured and tested differently from Spring MVC; choose guides matching your application model.

## 12. Checklist for Initializing a Spring Security Application

Before writing code:

- Determine application type: Spring MVC/Servlet or Spring WebFlux/reactive.
- Choose compatible Spring Boot and Java versions; let the BOM manage Spring Security modules.
- For basic Spring MVC, use `spring-boot-starter-web` and `spring-boot-starter-security`.
- Add `spring-boot-starter-test` and `spring-security-test` in test scope.
- Declare `SecurityFilterChain` for the right endpoints; define explicit rules and deny undeclared routes.
- Choose suitable authentication: Basic for demos, session/form or bearer tokens for production as needed.
- Choose `PasswordEncoder` and user management appropriately if using passwords; never store plaintext.
- Enable CSRF per threat model; define CORS/headers/session policies if browser clients exist.
- Design action- and object-level permission checks in services; HTTP roles alone are not enough.
- Verify with unit + integration tests: anonymous, valid user, insufficient privilege, wrong token/password, missing/invalid CSRF, different owner, wrong tenant.
- Use `dependencies` / `dependencyInsight` to diagnose the classpath rather than guessing modules.
- When upgrading versions, consult documentation and run security regression tests.

## 13. Self-Check Questions

**1.** Why does `Authentication` belong to core while `SecurityFilterChain` belongs to web? How do their purposes differ?

**2.** How do `HttpSecurity` and `SecurityFilterChain` differ? Which module provides each?

**3.** An application has `spring-security-core` and `spring-security-crypto` without web filters. Does that automatically protect `GET /api/admin`?

**4.** Why can `PasswordEncoder.matches` return true while a request still receives HTTP 403?

**5.** Why do you need to add `spring-security-test` if `spring-boot-starter-test` is already present?

**6.** What does a passing `@WithMockUser(roles = "ADMIN")` test prove, and what does it leave unproven?

**7.** When `POST /notes` returns 403 due to a missing CSRF token, should you fix it by adding a dependency or reviewing how the test request is constructed?

**8.** In Spring Boot 3, should you declare all five modules with separate version numbers in the build file?

**Suggested Answers:**

1. Core holds the shared identity/authority model; web binds that mechanism into HTTP requests and filters.
2. `HttpSecurity` is a builder in config; `SecurityFilterChain` is the resulting filter chain object in web.
3. No. You need a filter chain and appropriate HTTP policies integrated.
4. A matching password only satisfies one authentication step; the user can still lack authorities, fail owner/tenant checks, or be blocked by CSRF.
5. Starter test provides general test infrastructure; security-test adds mock principals, CSRF helpers, security request post-processors, and MockMvc Security integration.
6. It verifies policy behavior for an assumed user with role ADMIN; it does not prove real passwords, tokens, providers, or `UserDetailsService`.
7. Inspect CSRF protection and use `with(csrf())` in tests when the model requires a token; do not disable protection just to make tests pass.
8. No. With Boot starters and the BOM, let dependency management choose aligned versions; only add extra modules for specific use cases.

### Official Documentation for Checking Your Exact Version

- [Spring Security – Getting Spring Security / Dependency Management](https://docs.spring.io/spring-security/reference/getting-spring-security.html)
- [Spring Security – Servlet Architecture / FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Crypto Module](https://docs.spring.io/spring-security/reference/features/integrations/cryptography.html)
- [Spring Security – Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Security – MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
