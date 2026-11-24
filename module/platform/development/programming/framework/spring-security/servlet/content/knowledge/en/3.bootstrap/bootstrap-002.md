# The core, web, config, crypto, and spring-security-test Components in Spring Security Servlet

A Spring Security application running on the Servlet stack is not protected by a single library in the sense of “add one dependency and you understand everything.” Spring Security splits responsibilities across multiple modules: **core** models identity and authorities; **web** brings security mechanisms into HTTP/Servlet; **config** wires those mechanisms into configuration; **crypto** provides tools to protect passwords and data; and **spring-security-test** helps verify behavior. Understanding these boundaries helps you pick the right dependencies, read the right classes, and diagnose configuration bugs instead of making random changes.

This lesson is scoped to **Spring Security Servlet, Java 17+, and Spring Boot 3.x/Spring Security 6.x**. The examples below use Spring Boot 3.3.5; when using another Boot branch, let Boot's BOM manage compatible Spring Security versions and check API changes for that version.

## 1. Map of the Five Modules

| Maven/Gradle artifact | Primary responsibility | Representative APIs/classes | Present where? |
| --- | --- | --- | --- |
| `org.springframework.security:spring-security-core` | Authentication model, users, authorities, security context, and shared contracts | `Authentication`, `GrantedAuthority`, `SecurityContext`, `SecurityContextHolder`, `AuthenticationManager`, `UserDetails`, `UserDetailsService` | Runtime |
| `org.springframework.security:spring-security-web` | **HTTP Servlet** integration, filter chain, request protection, session, CSRF, and HTTP error branch handling | `FilterChainProxy`, `SecurityFilterChain`, `BasicAuthenticationFilter`, `CsrfFilter`, `AuthorizationFilter`, `ExceptionTranslationFilter` | Servlet application runtime |
| `org.springframework.security:spring-security-config` | Java/DSL configuration, building the filter chain, and wiring authentication/authorization components | `HttpSecurity`, `@EnableWebSecurity`, `@EnableMethodSecurity`, `Customizer` | Runtime when configured via these APIs |
| `org.springframework.security:spring-security-crypto` | Encryption, hashing, and password verification APIs; standalone crypto utilities | `PasswordEncoder`, `BCryptPasswordEncoder`, `DelegatingPasswordEncoder`, `PasswordEncoderFactories` | Runtime when authenticating passwords or using crypto |
| `org.springframework.security:spring-security-test` | Support for simulating users, adding credentials/CSRF to test requests, Spring Test/MockMvc integration | `@WithMockUser`, `@WithUserDetails`, `SecurityMockMvcRequestPostProcessors.user`, `httpBasic`, `csrf`, `springSecurity()` | **Test only** (Gradle `testImplementation`/Maven `test`) |

These are **artifacts/modules**, not five independent request layers. One module contains multiple packages; package names often suggest responsibilities, but you should inspect actual dependencies rather than guessing which JAR a class belongs to.

Conceptual diagram when using Spring Boot Servlet:

~~~text
spring-boot-starter-web                 spring-boot-starter-security
  -> Spring MVC + Servlet container       -> Spring Security runtime libraries
                                             core / web / config / crypto
                  |                                    |
                  +------------ application -----------+
                                      |
                         SecurityFilterChain bean
                                      |
                     Servlet security filters + controller

testImplementation spring-boot-starter-test
testImplementation spring-security-test
                 -> JUnit + MockMvc + security test tools
~~~

The two Boot starters and the standalone artifact play distinct roles:

- `spring-boot-starter-web` provides the Servlet/Spring MVC foundation. It **does not automatically provide HTTP protection via Spring Security**.
- `spring-boot-starter-security` brings the required runtime modules onto the classpath and activates Boot's security auto-configuration. In a typical Boot application, you do not need to list the four `core/web/config/crypto` artifacts manually; inspect the dependency graph to see the resolved versions.
- `spring-security-test` **is not automatically added** just because you have the security starter. It must be declared separately for tests.
- Components for OAuth2 login, OAuth2 resource server, SAML2, etc., live in other specialized artifacts. Do not assume “having core/web/config gives every authentication mechanism automatically.”

Key point to remember: **module** answers “what is the library responsible for?”, while **bean/filter** answers “which components does a request flow through at runtime?”. These two questions complement each other.

## 2. `spring-security-core`: Identity, Authorities, and Context

### 2.1. Foundational Contracts

`Authentication` represents authentication information in Spring Security. It can hold the principal, credentials, authorities, details, and the `isAuthenticated()` state. During authentication, an initial `Authentication` may hold unverified credentials; after success, `AuthenticationManager` returns an authenticated result. Therefore, **do not assume merely having an Authentication object means login has succeeded**.

`GrantedAuthority` represents a permission in a form understood by security policies, typically a string such as `ROLE_READER` or `REPORT_VIEW`. “Role” is a common convention over authorities: `hasRole("ADMIN")` typically checks for `ROLE_ADMIN`, whereas `hasAuthority("ADMIN")` checks for the exact string `ADMIN`. The prefix convention can be customized; this lesson uses the default.

`SecurityContext` holds the current `Authentication`; `SecurityContextHolder` is the standard access point to the context in the current execution flow. In a Servlet application, filters manage setting and clearing the context at appropriate request boundaries. Do not rely on assuming “ThreadLocal automatically follows every thread,” especially when using `@Async`, executors, or background tasks.

`AuthenticationManager` receives an authentication request and returns a result or throws an error; `AuthenticationProvider` is a strategy capable of authenticating a specific token type. For username/password, `UserDetailsService` supplies user data to the appropriate authentication flow, while `PasswordEncoder` checks the submitted password against the stored hash.

### 2.2. Core **Does Not Mean** Automatic HTTP Blocking

Merely having the `Authentication` or `UserDetailsService` interface on the classpath is not enough to protect `GET /admin`. Connecting authentication to Servlet requests lives in **web**, while URL access rules are usually declared through **config**.

A way to locate classes when reading code:

| When you need to know... | Start from |
| --- | --- |
| Which object represents the caller? | `Authentication`, `getPrincipal()` |
| What authorities does the caller have? | `getAuthorities()`, `GrantedAuthority` |
| Where is the current context stored? | `SecurityContextHolder` |
| How are credentials verified? | `AuthenticationManager`, `AuthenticationProvider` |
| Where is the user loaded from? | `UserDetailsService` and the application's data source implementation |
| At which step is a URL blocked? | Move to the `web` module and `SecurityFilterChain` configuration |

**Note:** `UserDetailsService.loadUserByUsername()` is not an HTTP controller and does not decide URL access on its own; it is a data source for an authentication mechanism.

## 3. `spring-security-web`: The Servlet Request Interception Point

A Spring MVC request passes through the Servlet filter chain before reaching `DispatcherServlet`. Spring Security uses `DelegatingFilterProxy` to bridge the Servlet container's filter chain to a Spring bean usually named `springSecurityFilterChain`, managed by `FilterChainProxy`.

`FilterChainProxy` selects the `SecurityFilterChain` matching the request. An application can declare multiple chains for `/api/**` and other web pages; **which chain is chosen** depends on the matchers and chain order. The specific filters depend on which security mechanisms are enabled; there is no single fixed order that applies to every project.

~~~text
HTTP request
    |
Servlet filter chain
    |
DelegatingFilterProxy
    |
FilterChainProxy
    |
SecurityFilterChain matching the request
    |-- handle SecurityContext
    |-- authentication filters (if the corresponding mechanism is enabled)
    |-- CSRF check when applicable
    |-- authorization evaluation
    |-- exception translation / entry point / access denied handler
    |
    +--> allow -> DispatcherServlet -> controller
    |
    +--> deny -> 401 / 403 / redirect ... depending on the situation
~~~

Examples of responsibilities belonging to `web`:

- `BasicAuthenticationFilter` can read the `Authorization: Basic ...` header, build an authentication request, and invoke the authentication layer. Not every application uses HTTP Basic.
- `AuthorizationFilter` enforces configured authorization rules.
- `CsrfFilter` handles CSRF protection when enabled and the request falls within the checked scope.
- `ExceptionTranslationFilter` bridges certain authentication/authorization exceptions to an entry point or access-denied handler. Some authentication filters can also invoke the entry point directly.
- Components handling sessions and `SecurityContext` depend on configuration; do not treat an HTTP Basic header as proof that the application has disabled sessions.

**401 vs. 403:** an unauthenticated request can receive a 401 challenge when using Basic; an authenticated request lacking permissions typically receives 403. A POST request missing a CSRF token can also receive 403. With form login, the entry point may return 302. Always cross-check the active mechanisms.

## 4. `spring-security-config`: Policy Declaration and Module Wiring

Instead of manually creating and ordering all Servlet filters, applications typically declare a `SecurityFilterChain` bean and configure it via `HttpSecurity`. This API belongs to `spring-security-config`; the resulting bean uses components from `web` and `core`.

The following minimal configuration example illustrates the DSL **shape**, not a standalone runnable application:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .requestMatchers("/admin").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Keep these distinctions clear:

- `requestMatchers("/public")` only selects requests to apply an **authorization rule**, not which security chain to pick. When multiple chains exist, `securityMatcher(...)` at the `HttpSecurity` level and `@Order` precedence are a separate concern.
- `permitAll()` allows a URL under this policy; it does not bypass all security filters.
- `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority under the default convention.
- `anyRequest().authenticated()` goes last as a fallback; rule order matters.
- `httpBasic(...)` enables HTTP Basic. If form login is not enabled, do not assume browsers will always be redirected to a login page.
- `http.build()` builds the filter chain. It is not a command that processes a request immediately.

In a Spring Boot 3.x Servlet application, defining a `@Bean` of type `SecurityFilterChain` is the standard way to replace Boot's default web security policy. `@EnableWebSecurity` is useful in plain Spring Security configuration, but does not need to be added as a mandatory ritual in every Boot application. `@EnableMethodSecurity` enables annotations such as `@PreAuthorize` at the method layer; it is a complementary mechanism, not a prerequisite for `authorizeHttpRequests` to work.

## 5. `spring-security-crypto`: Intentional Password Handling

`PasswordEncoder` provides two key operations: `encode(rawPassword)` to produce the value to store, and `matches(rawPassword, encodedPassword)` to verify against it. Do not compare encoded password strings by doing `equals(encode(raw))` yourself: salted algorithms like BCrypt typically produce a different hash every time the same password is encoded.

~~~java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String stored = encoder.encode("example-password");
boolean accepted = encoder.matches("example-password", stored);
boolean rejected = encoder.matches("wrong-password", stored);

System.out.println(accepted);
System.out.println(rejected);
~~~

The snippet above is an **illustrative code fragment** that needs imports for `org.springframework.security.crypto.password.PasswordEncoder` and `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`, placed inside a method. The two output lines are always:

~~~text
true
false
~~~

`stored` is a salted hash string, **not fixed across runs**, so do not put a sample hash into `assertEquals` checks. `BCryptPasswordEncoder` is a convenient illustrative choice; the algorithm and work factor in a real product must be chosen according to security policy and server capacity.

`DelegatingPasswordEncoder` supports distinguishing multiple algorithms via prefixes formatted like `{bcrypt}...`, depending on the configured encoder id. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` provides a pre-registered set of encoders. When changing encoders, do not simply swap the bean and assume all legacy hashes immediately stay compatible: consider stored formats, migration, and password verification.

**Do not use** plaintext passwords, `NoOpPasswordEncoder`, or hardcoded credentials in real deployment configurations. The in-memory user example below is solely for learning/self-testing.

## 6. `spring-security-test`: Testing Rules, Identity, and Authentication Mechanisms

Tests do not only verify that a controller returns the right body; for protected endpoints, you must prove both that **unauthorized requests are rejected at the right time** and that **valid requests pass according to policy**. `spring-security-test` supports two test groups with different goals:

1. **Simulating SecurityContext:** `@WithMockUser` or `.with(user(...))` creates a test identity with the desired authorities. This tests authorization and controller behavior, and **does not prove that a real password was checked**.
2. **Sending credentials over the protocol:** `.with(httpBasic("reader","reader-pass"))` sets the HTTP Basic header so the application's filter and `AuthenticationProvider` process it. This verifies the real authentication flow in a MockMvc context.
3. **Simulating CSRF:** `.with(csrf())` supplies a valid CSRF token for the test request; also verify the missing-token case so you do not accidentally disable protection.
4. **Filter chain integration:** use Spring Test/MockMvc configured with Spring Security, such as Boot's `@SpringBootTest` + `@AutoConfigureMockMvc`, or configure `springSecurity()` with a manually built MockMvc. If you forget to apply the security filters, tests can falsely return 200 while runtime returns 401/403.

`@WithMockUser` does not require the username to exist in a database or in-memory store. That is an advantage for testing authorization independently, and a limitation when you need to test the password encoder or authentication provider.

## 7. Runnable Example with Java 17, Spring Boot 3.x, and MockMvc

The example below separates classes by responsibility: application startup; configuration creating `SecurityFilterChain`/users/encoder; controller serving HTTP; and tests executing requests with MockMvc. It lets you inspect **all five modules** in one small application.

### 7.1. Project Structure

~~~text
security-modules-demo/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/java/demo/security/
    │   ├── SecurityModulesApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/demo/security/
        └── SecurityModulesApplicationTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'security-modules-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

**Why not declare versions on each Spring Security artifact?** The dependency-management plugin imports the BOM matching the Boot version, so Boot selects compatible security versions. Forcing a separate version on `spring-security-core` while `web/config/crypto` still follow the BOM can create an inconsistent classpath. In projects using a version catalog or another Gradle platform, maintain the same version-alignment principle.

File `src/main/java/demo/security/SecurityModulesApplication.java`:

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityModulesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityModulesApplication.class, args);
    }
}
~~~

File `src/main/java/demo/security/SecurityConfiguration.java`:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

File `src/main/java/demo/security/DemoController.java`:

~~~java
package demo.security;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    public String currentUser(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    public String adminArea() {
        return "admin area";
    }

    @PostMapping("/notes")
    public String createNote() {
        return "created";
    }
}
~~~

Path breakdown:

- `/public`: `permitAll`, no credentials needed.
- `/me`: under `anyRequest().authenticated()`, requires login; when valid, the controller reads `Principal`.
- `/admin`: requires authority `ROLE_ADMIN`; `reader` only has `ROLE_READER`.
- `POST /notes`: requires authentication **and** is subject to CSRF protection by default. Logging in properly via Basic without sending a CSRF token still returns 403; do not rush to blame `hasRole`.
- Passwords are hashed with `BCryptPasswordEncoder` when the user store bean is created. This lesson does not use a database, OAuth2, or API tokens; those are separate options for advanced lessons.

### 7.2. Testing Both Allow and Deny Branches

File `src/test/java/demo/security/SecurityModulesApplicationTests.java`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityModulesApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicEndpointDoesNotRequireCredentials() throws Exception {
        mockMvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAreAuthenticated() throws Exception {
        mockMvc.perform(get("/me").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotAccessAdmin() throws Exception {
        mockMvc.perform(get("/admin").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void syntheticAdminIdentityCanPassAuthorization() throws Exception {
        mockMvc.perform(get("/admin").with(user("mock-admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin area"));
    }

    @Test
    @WithMockUser(username = "simulated-reader", roles = "READER")
    void annotationInjectsTestIdentity() throws Exception {
        mockMvc.perform(get("/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("hello simulated-reader"));
    }

    @Test
    void csrfProtectionAppliesToStateChangingRequests() throws Exception {
        mockMvc.perform(post("/notes").with(user("reader")))
            .andExpect(status().isForbidden());

        mockMvc.perform(post("/notes").with(user("reader")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }
}
~~~

Each test verifies a specific contract:

| Test | Observed components | What it proves |
| --- | --- | --- |
| `publicEndpointDoesNotRequireCredentials` | Config + web | Public URL passes the policy properly. |
| `privateEndpointRequiresAuthentication` | Web/filter entry point | Unauthenticated client cannot access private endpoints. |
| `validBasicCredentialsAreAuthenticated` | Web + core + crypto | Basic header goes through real authentication; valid password is accepted. |
| `wrongPasswordIsRejected` | Core + crypto + web | Wrong password is rejected. |
| `authenticatedReaderCannotAccessAdmin` | Core authority + config + web | Valid authentication does not mean sufficient authorization. |
| `syntheticAdminIdentityCanPassAuthorization` | Security test + config | Simulated identity with `ROLE_ADMIN` passes the rule, **without testing password**. |
| `annotationInjectsTestIdentity` | `@WithMockUser` + security test | Controllers can be tested with a test principal without a database. |
| `csrfProtectionAppliesToStateChangingRequests` | Web CSRF + security test | POST without token is blocked; with a valid token it is permitted. |

In tests using `@AutoConfigureMockMvc`, Spring Boot integrates security filters into MockMvc by default. If you manually call `MockMvcBuilders.webAppContextSetup(context).build()`, make sure to add `.apply(springSecurity())`; omitting this step can cause tests to miss real HTTP protection behavior.

Tests in `spring-security-test` are tools for **setting up test conditions and assertions**; the production application must not depend on this artifact in `implementation`.

### 7.3. How to Run and Expected Results

For a project that already has a Gradle wrapper, run:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows use `gradlew.bat test` and `gradlew.bat bootRun`. If you just created the files from the example without a wrapper yet, you can run `gradle test` / `gradle bootRun` with a compatible installed Gradle, or generate the wrapper first. This example uses Spring libraries, so `javac`/`java` directly is not enough without setting up the classpath.

Once the application starts successfully (default port 8080), open another terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
curl -i -u reader:reader-pass -X POST http://localhost:8080/notes
~~~

Key verification results; header order/values may vary by environment:

| Request | Expected status | Body on success |
| --- | --- | --- |
| GET `/public` without auth | 200 | `public` |
| GET `/me` without auth | 401 | No specific body required |
| GET `/me` with `reader` and valid password | 200 | `hello reader` |
| GET `/admin` with `reader` | 403 | No specific body required |
| GET `/admin` with `admin` and valid password | 200 | `admin area` |
| POST `/notes` with valid Basic, **without CSRF token** | 403 | No specific body required |

The last POST command intentionally demonstrates **CSRF staying enabled by default**; the example does not expose an HTTP endpoint to fetch a CSRF token, so use the MockMvc `.with(csrf())` test to verify the success branch. Do not turn off CSRF just to make a test POST return 200. For token-only API applications that do not use cookies/sessions, the decision to enable/disable CSRF must be based on the actual authentication model and threat model.

## 8. Observing the Dependency Graph: Checking Which Modules Actually Loaded

You do not necessarily have to inspect every JAR. Gradle directly answers whether a module appears on the classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
~~~

In `runtimeClasspath`, look for `spring-security-core`, `spring-security-web`, `spring-security-config`, and `spring-security-crypto`; in `testRuntimeClasspath`, also look for `spring-security-test`. Use `dependencyInsight` to see **why** a module was selected and which version actually resolved.

The `dependencies` command shows you the **graph**, not direct proof that Spring registered the right beans or which filters a request goes through. To answer runtime questions, go on to inspect the `SecurityFilterChain` bean and run HTTP tests.

A way to trace failures:

1. `ClassNotFoundException`/`NoClassDefFoundError` in `org.springframework.security...`: identify the module containing the class, compile/runtime classpaths, and version skew.
2. Error initializing `SecurityFilterChain`: inspect the bean/config and policies declared via `HttpSecurity`; do not rush to add `spring-security-test` to runtime.
3. Password is always rejected: inspect `PasswordEncoder.matches`, stored hash format, and the injected encoder. Do not compare BCrypt hashes against a fixed string.
4. `@WithMockUser` test passes while real Basic returns 401: inspect the user store, provider, and password; simulated-identity tests do not verify the credentials path.
5. `/admin` returns 403 even though the user is logged in: check authorities and rules. `ROLE_ADMIN` differs from `ROLE_READER`; 403 can also come from CSRF on state-changing requests.
6. Test returns 200 while real execution returns 401: check whether MockMvc has the security filter chain applied.
7. Multiple `SecurityFilterChain`s: check `securityMatcher`, `@Order`, and which chain matches the request first. Inner `requestMatchers` do not decide which chain is selected.

## 9. When Should You Add or Swap Modules?

| Need | Module/configuration to check |
| --- | --- |
| Only need types like `Authentication` in a shared library | `core` fits at the API level; not HTTP security yet |
| Want to protect Spring MVC endpoints running on a Servlet container | `web` + `config` + required authentication/crypto components |
| Want to write a policy bean using `HttpSecurity` | `config` |
| Want to hash and verify passwords | `crypto` |
| Want to test Spring Security with MockMvc/annotations | `spring-security-test` in test scope |
| Want to accept bearer JWTs as a resource server | Look for a specialized artifact like `spring-boot-starter-oauth2-resource-server`, outside the five basic modules |
| Reactive Spring WebFlux project | Use reactive APIs/filters (e.g., `SecurityWebFilterChain`); do not apply Servlet `HttpSecurity` and `FilterChainProxy` verbatim |

In **Spring Boot Servlet**, starting from the Web + Security + test starters is simple and stable. In plain Spring Framework without Boot, you must declare compatible dependencies manually and configure registration of `DelegatingFilterProxy`/Spring Security with the Servlet context. Simply having JARs on the classpath does not replace integrating the request filter into the container.

To update versions, prefer centralized version management via the Spring Boot BOM or equivalent mechanism, then run tests including 401/403 and password verification. Do not upgrade one runtime module individually while other modules remain locked at incompatible versions.

## 10. Self-Check Exercises

1. Point to the imports in `SecurityConfiguration.java` and classify each class under `core`, `web`, `config`, or `crypto`. Explain why one configuration bean can use types from multiple artifacts.
2. Remove the `spring-security-test` declaration from `testImplementation` (in a trial copy only), run test compilation, and record which imports fail to resolve; then restore the dependency. Why can the runtime application still run normally?
3. Change `reader`'s role from `READER` to `ADMIN` and re-run authorization tests: which test must change its expectation and why? Do not leave old tests assuming `reader` will always lack permission.
4. Compare `.with(user("reader"))` and `.with(httpBasic("reader","reader-pass"))`: which test exercises the application's password authentication, and which only constructs a principal?
5. For `POST /notes`, predict the response when (a) not logged in, (b) logged in properly but missing a CSRF token, (c) using a mock user with a CSRF token in MockMvc. Verify in practice, noting that a request can be rejected by the CSRF filter before reaching the login challenge step.
6. Use `dependencyInsight` to confirm the selected version for `spring-security-core` and the dependency source that pulled that module in.
7. Explain why having `spring-security-web` on the classpath does not by itself prove `/admin` is protected: you must check the `SecurityFilterChain` bean, matchers, and Servlet filter integration.
8. If you later add OAuth2/JWT or method security, state which module roles remain core and which parts are extended.

**Summary of technical responsibilities:** `core` defines *who and with what authorities*; `web` brings enforcement into *Servlet requests*; `config` decides *wiring and policy*; `crypto` supports *safe secret verification*; `spring-security-test` helps *prove behavior through tests*. Reading these boundaries accurately helps you choose dependencies intentionally and avoid confusing classpath, authentication, authorization, and test-setup errors.
