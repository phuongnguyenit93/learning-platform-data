# Setting Up `spring-boot-starter-webflux`, `spring-boot-starter-security`, and `spring-security-test`

> **Topic:** Spring Security – reactive  
> **Knowledge group:** Application Bootstrap  
> **Hands-on goal:** Have a runnable Spring Boot WebFlux application, an HTTP protection configuration using Spring Security reactive, and an authentication/authorization test suite using `WebTestClient` with `spring-security-test`.

## 1. Understanding the role of each dependency

In a reactive application, **WebFlux** provides the web model and asynchronous processing based on `Publisher` (`Mono`/`Flux`), **Spring Security** protects requests and manages identity/access rights, and **Spring Security Test** provides tools for mocking identities and testing security policies. These are three distinct responsibilities that integrate when run together.

| Dependency | Scope | What does it provide? | Where is it used? |
| --- | --- | --- | --- |
| `org.springframework.boot:spring-boot-starter-webflux` | Runtime/compile | Spring WebFlux, Reactor, REST controller or functional routing support, default Reactor Netty server | `@RestController`, `Mono`, `Flux`, reactive HTTP handling |
| `org.springframework.boot:spring-boot-starter-security` | Runtime/compile | Spring Security core, Spring Security configuration, and web protection integration; with WebFlux it uses reactive components | `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveAuthenticationManager` |
| `org.springframework.security:spring-security-test` | **Test only** | `mockUser()`, `springSecurity()`, `csrf()`, `@WithMockUser`, security testing utilities | `src/test/java`, `WebTestClient`, JUnit |
| `org.springframework.boot:spring-boot-starter-test` | Test only | JUnit Jupiter, Spring Boot Test/Spring Test, AssertJ, Mockito, and common test libraries | Running `@SpringBootTest`, assertions, and test context |
| `io.projectreactor:reactor-test` | Test only | `StepVerifier`, `TestPublisher` for testing Reactor publishers | Unit testing `Mono`/`Flux` chains independently of HTTP |

**Do not confuse the two test groups:** `spring-boot-starter-test` brings the JUnit and Spring Test foundation; `spring-security-test` adds security-specific utilities. To test secured WebFlux endpoints conveniently, you need both. `reactor-test` is useful for testing operators/publishers, but it does not replace `WebTestClient`.

**Do not mix the two web stacks out of habit:** `spring-boot-starter-web` is the Spring MVC/Servlet foundation. When both `starter-web` and `starter-webflux` are present, Spring Boot typically chooses a Servlet application. To learn the reactive configuration accurately, use only `spring-boot-starter-webflux` in this example. WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity`; Spring MVC uses `SecurityFilterChain` and `HttpSecurity`.

### From dependencies to requests

```text
spring-boot-starter-webflux
    └── WebFlux WebHandler + Reactor Netty + Mono/Flux
               │
HTTP request ──┼──> SecurityWebFilterChain (spring-boot-starter-security)
               │         ├── authenticate caller
               │         └── check authority/role
               └──> @RestController / reactive service ──> response

JUnit + Spring Test (spring-boot-starter-test)
    └── WebTestClient + SecurityMockServerConfigurers (spring-security-test)
                └── send simulated request, check 200 / 401 / 403
```

Spring Security reactive attaches `Authentication` to `SecurityContext` inside the Reactor `Context`. Never assume a WebFlux request will run for its entire lifetime on a single fixed thread.

## 2. Prerequisites and project initialization

The standalone example below uses **Java 17+** and **Spring Boot 3.5.16**, a concrete version so dependencies are managed consistently. You need Maven 3.6.3+ (if choosing Maven) or a Gradle version compatible with Spring Boot 3.5 (if choosing Gradle). When bringing this into another project, choose the Spring Boot branch supported by your project and let Spring Boot's BOM/plugin manage the versions of Spring Framework, Spring Security, and Reactor.

You can initialize via [Spring Initializr](https://start.spring.io/) and select:

1. **Project:** Maven or Gradle; **Language:** Java; **Java:** 17 or higher.
2. **Dependencies:** **Spring Reactive Web** (WebFlux), **Spring Security**.
3. Add `spring-security-test` to test dependencies if the project generator did not include it; keep `spring-boot-starter-test` and add `reactor-test` when you need to test `Mono`/`Flux`.
4. Place Java sources under the same root package so `@SpringBootApplication` and `@SpringBootTest` can discover configurations.

Do not add separate versions for the three main dependencies when using the Spring Boot parent/BOM. Manually mixing versions from different Spring Security, Spring WebFlux, or Reactor lines can cause `NoSuchMethodError`, class conflicts, or broken test configuration.

## 3. Maven build configuration: complete and runnable

Complete file structure of the hands-on lab:

```text
reactive-security-setup/
├── pom.xml
└── src/
    ├── main/java/demo/reactivesecurity/
    │   ├── ReactiveSecurityApplication.java
    │   ├── SecurityConfiguration.java
    │   └── SampleController.java
    └── test/java/demo/reactivesecurity/
        └── ReactiveSecurityApplicationTests.java
```

### 3.1. File `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-security-setup</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>reactive-security-setup</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

Explanation:

- `spring-boot-starter-parent` applies version management, build configuration, and plugins matching the chosen Spring Boot version. There is no need to fill in separate `<version>` tags for `starter-webflux`, `starter-security`, `starter-test`, `spring-security-test`, or `reactor-test`.
- `spring-security-test` has `<scope>test</scope>`: security mock classes are compiled and used in tests, not packaged as runtime dependencies of the application.
- `spring-boot-starter-test` is the test framework foundation; `spring-security-test` is the security extension.
- `reactor-test` is not a strict requirement for writing simple `WebTestClient` tests, but should be included when verifying publishers with `StepVerifier`.

## 4. If the project uses Gradle (Groovy DSL)

Replace `pom.xml` with `settings.gradle` and `build.gradle` below; **choose only one build system** for the example, there is no need to keep both Maven and Gradle in the same project.

**`settings.gradle`**

```groovy
rootProject.name = 'reactive-security-setup'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In Gradle, `implementation` corresponds to dependencies needed to compile/run the application; `testImplementation` is only needed to compile/run tests. The Spring Boot plugin coordinates with dependency management to use compatible versions. If using Kotlin DSL, the syntax differs; this snippet is for `build.gradle` (Groovy).

## 5. Sample WebFlux application: verifying the starters work together

The following Java files use **package `demo.reactivesecurity`**. Copy the exact paths and package so Spring Boot discovers the classes.

### 5.1. `src/main/java/demo/reactivesecurity/ReactiveSecurityApplication.java`

```java
package demo.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
```

`@SpringBootApplication` is the entry point, automatically scanning classes in the same package and subpackages. When dependencies are right, Boot starts a WebFlux application with embedded Reactor Netty by default.

### 5.2. `src/main/java/demo/reactivesecurity/SecurityConfiguration.java`

```java
package demo.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/reports").hasRole("READER")
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails guest = User.withUsername("guest")
            .password("{noop}guest123")
            .roles("GUEST")
            .build();

        return new MapReactiveUserDetailsService(reader, guest);
    }
}
```

Key points to understand:

- `@EnableWebFluxSecurity` enables security configuration for WebFlux; Spring Security uses **`WebFilter`** to integrate into the reactive web stack.
- `SecurityWebFilterChain` and `ServerHttpSecurity` are reactive APIs. Do not replace them with Servlet's `SecurityFilterChain`, `HttpSecurity`, or `@EnableWebSecurity`.
- `/api/public` is publicly accessible; `/api/reports` requires role `READER`; remaining paths require an authenticated user.
- `roles("READER")` grants authority `ROLE_READER`; `hasRole("READER")` checks the string `ROLE_READER` by default.
- `httpBasic` lets you test with HTTP Basic credentials; `formLogin` is disabled so the demo API does not redirect to an HTML login page.
- `MapReactiveUserDetailsService` is an in-memory user store suitable for demos/learning materials. Real systems typically use a user source and a properly configured `PasswordEncoder`.
- **`{noop}` is only for local examples:** it accepts unhashed passwords. Real applications must store strong hashes (e.g., BCrypt/Argon2), use HTTPS, and never commit passwords into source code. The example does not disable CSRF; the test requests below are all GETs.

If you only add `starter-security` without declaring rules yourself, Spring Boot/Spring Security may protect all requests using the default configuration, using a generated default user or one provided by configuration. Seeing 401 right after adding the dependency is normal default protection behavior, not WebFlux failing to work.

### 5.3. `src/main/java/demo/reactivesecurity/SampleController.java`

```java
package demo.reactivesecurity;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SampleController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public OK");
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> "user: " + authentication.getName());
    }
}
```

`Mono<String>` represents a reactive return type. The `/api/me` endpoint illustrates reading the authenticated principal via the **Reactor security context**; do not take identity from query parameters, and do not rely on a regular `ThreadLocal` as a source across the pipeline.

## 6. Testing Spring Security reactive with `spring-security-test`

The goal is to verify both scenarios:

1. **Real authentication:** send username/password via HTTP Basic, allowing the Security chain to authenticate against `MapReactiveUserDetailsService`.
2. **Isolated authorization:** use `mockUser()` to create a fake authenticated principal for a request, testing roles without entering passwords or calling a real identity provider.

In this example we use `@SpringBootTest` to load the real application configuration, then bind `WebTestClient` to the `ApplicationContext` with **`springSecurity()`** to activate security test support. This approach does not require running a real server on a TCP port.

### 6.1. `src/test/java/demo/reactivesecurity/ReactiveSecurityApplicationTests.java`

```java
package demo.reactivesecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveSecurityApplicationTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointIsAccessibleWithoutLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void reportsRequireAuthentication() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void realBasicReaderCanReadReports() {
        client.get().uri("/api/reports")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void realBasicGuestIsForbidden() {
        client.get().uri("/api/reports")
            .headers(headers -> headers.setBasicAuth("guest", "guest123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordIsUnauthorized() {
        client.get().uri("/api/reports")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedReaderCanReadReports() {
        client.mutateWith(mockUser("alice").roles("READER"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void mockedGuestCannotReadReports() {
        client.mutateWith(mockUser("bob").roles("GUEST"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Why does this test need all three starters/libraries mentioned?**

- `WebTestClient` checks requests/responses in WebFlux style without requiring a real server. This is the Spring Test API used with WebFlux, not `MockMvc`.
- `@SpringBootTest`, `@Test`, and `@BeforeEach` require the Spring Boot test foundation and JUnit.
- `SecurityMockServerConfigurers.springSecurity()` and `mockUser()` live in **`spring-security-test`**. Without this test dependency, importing those two methods will not compile.
- `mockUser("alice").roles("READER")` creates a request with a simulated authenticated user and authority `ROLE_READER`. It does **not** test the real password-checking mechanism.
- Only tests sending Basic credentials verify the authentication step based on `UserDetails` and password; mock user tests primarily verify authorization rules.
- `@SpringBootTest` + `bindToApplicationContext` keeps `SecurityConfiguration` in the context. When using `@WebFluxTest` to load only the controller, you must `@Import(SecurityConfiguration.class)` if you want to test this custom policy; slice tests do not automatically load all application configurations.

### 6.2. Result matrix and how to interpret failures

| Test | Principal/credentials | Rule | Expected HTTP |
| --- | --- | --- | --- |
| `publicEndpointIsAccessibleWithoutLogin` | None | `permitAll` | **200** |
| `reportsRequireAuthentication` | None | Endpoint requires `ROLE_READER` | **401** |
| `realBasicReaderCanReadReports` | Basic `reader` correct password | Has `ROLE_READER` | **200** |
| `realBasicGuestIsForbidden` | Basic `guest` correct password | Only has `ROLE_GUEST` | **403** |
| `wrongPasswordIsUnauthorized` | Basic wrong password | Authentication fails | **401** |
| `mockedReaderCanReadReports` | Mock `alice`, role `READER` | Has `ROLE_READER` | **200** |
| `mockedGuestCannotReadReports` | Mock `bob`, role `GUEST` | Missing `ROLE_READER` | **403** |

**401**: valid identity has not been proven for the protected resource. **403**: identity was accepted but lacks sufficient permissions under this policy. Tests should clearly distinguish these two scenarios, not merely assert "request failed".

### 6.3. Other testing utilities worth knowing

- **`@WithMockUser(username = "alice", roles = "READER")`:** another way to set a mock security context for tests. With WebFlux, ensure Spring Security Test is integrated into the test context/`WebTestClient`; the main example uses `mockUser` to clearly show per-request application.
- **`mockUser().authorities(...)`:** useful if the policy uses fine-grained permissions such as `report:read` rather than roles. `roles("READER")` and `authorities(new SimpleGrantedAuthority("report:read"))` express two different rules.
- **`csrf()`:** when writing POST/PUT/PATCH/DELETE tests in an application with CSRF protection enabled, a valid request may need `client.mutateWith(csrf())` before `.post()`. Do not disable CSRF just to make tests pass; decide the CSRF policy based on cookies/session/bearer tokens and the client model.
- **`mockJwt()`:** only applies when a suitable OAuth2 Resource Server configuration is present; it does not turn into real JWT authentication simply because `spring-security-test` was added.
- **`StepVerifier`:** tests the signal sequence of `Mono`/`Flux` in unit tests, complementing HTTP tests with `WebTestClient`.
- **`@AutoConfigureWebTestClient`:** Spring Boot can auto-provision a `WebTestClient` for `@SpringBootTest`; the example uses `bindToApplicationContext(...).apply(springSecurity())` to explicitly show how Spring Security Test is wired in.

Additional example **illustrating only a simple publisher**, runnable if placed in a test class with the `reactor-test` dependency:

```java
// Example method in a JUnit test class importing Mono and StepVerifier:
@Test
void monoEmitsOneValueAndCompletes() {
    StepVerifier.create(Mono.just("ready"))
        .expectNext("ready")
        .verifyComplete();
}
```

To use it, add imports for `org.junit.jupiter.api.Test`, `reactor.core.publisher.Mono`, and `reactor.test.StepVerifier` in the corresponding test file. This snippet does not replace HTTP security testing.

## 7. Running the project, reading results, and verifying dependencies

### 7.1. Checking the environment

```bash
java -version
mvn -version
```

Expect `java -version` to show Java 17 or higher and `mvn -version` to use a compatible JDK. If using the `mvnw` wrapper generated by Spring Initializr, use `./mvnw` (Linux/macOS) or `.\mvnw.cmd` (Windows) instead of `mvn`.

### 7.2. Running tests

```bash
mvn clean test
```

Logical outcome to achieve: **7 tests run successfully, 0 failures, 0 errors**. Keep in mind that Maven output lines (timing, JUnit provider name, plugin counts) vary by environment; check the `BUILD SUCCESS` line and reports in `target/surefire-reports/`.

If using Gradle:

```bash
gradle test
```

When a Gradle wrapper is present, use `./gradlew test` on Linux/macOS or `.\gradlew.bat test` on Windows. View the HTML report at `build/reports/tests/test/index.html`.

### 7.3. Starting the server and calling APIs manually

```bash
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/reports
curl -i -u guest:guest123 http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/me
```

On Windows PowerShell, use `curl.exe` instead of `curl` if `curl` is aliased to another PowerShell command.

Expected results:

| HTTP request | Status | Body on success |
| --- | --- | --- |
| `GET /api/public`, no credentials | 200 | `public OK` |
| `GET /api/reports`, no credentials | 401 | Not fixed |
| `GET /api/reports` with `reader:reader123` | 200 | `reports OK` |
| `GET /api/reports` with `guest:guest123` | 403 | Not fixed |
| `GET /api/me` with `reader:reader123` | 200 | `user: reader` |

Do not rely on the full response headers or body of 401/403 errors to verify the lesson: error formats may be changed by Spring Boot/Spring Security exception handling configuration.

### 7.4. Checking classpath scopes

With Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

With Gradle:

```bash
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
```

Look for `spring-security-test` on the **test** classpath; it does not need to appear in the application's packaged runtime classpath. `spring-security-test` belongs in test because production applications do not use `mockUser` to make authorization decisions.

## 8. Common configuration mistakes and how to fix them

| Symptom | Cause worth checking | How to fix |
| --- | --- | --- |
| Cannot find import `mockUser` or `springSecurity` | Missing `spring-security-test` in test dependencies, wrong Servlet package | Add `org.springframework.security:spring-security-test` with test scope, import `...test.web.reactive.server.SecurityMockServerConfigurers` |
| Cannot find `@Test` / `@SpringBootTest` | Missing `spring-boot-starter-test` | Declare test starter and run with JUnit Platform |
| Using `MockMvc`, `HttpSecurity`, `SecurityFilterChain` in a WebFlux demo | Confusing Servlet stack with reactive | Use `WebTestClient`, `ServerHttpSecurity`, `SecurityWebFilterChain` |
| Public request returns 401 | Missing `permitAll` rule, path mismatch, or security config not loaded | Check chain, `pathMatchers` order, and exact URL |
| User has correct password but gets 403 | Authenticated, missing role/authority | Remember `hasRole("READER")` needs `ROLE_READER`; check `roles`/`authorities` |
| Has role `READER` but passes `"READER"` in `hasAuthority` | Confusing `hasRole` and `hasAuthority` | For roles use `hasRole("READER")` or `hasAuthority("ROLE_READER")` |
| Mock user test passes but real login returns 401 | `mockUser` test bypassed credential verification | Add real HTTP Basic/JWT integration tests, check user store/password encoder |
| `@WebFluxTest` differs from production security policy | Slice test does not automatically include all custom configs | Import the SecurityConfiguration to test or use `@SpringBootTest` |
| Authorized POST still gets 403 | Missing CSRF token when CSRF mechanism is enabled | Use `csrf()` appropriately in security tests; design CSRF for the real client model |
| `NoSuchMethodError` during tests or runtime | Forcing Spring Security, Reactor, or Spring Framework versions out of sync with Spring Boot BOM | Remove unnecessary versions, check dependency tree, and rebuild |
| App runs as MVC despite adding WebFlux | Both `spring-boot-starter-web` are present | Actively choose one web stack; a reactive demo only needs `starter-webflux` |
| `ClassNotFoundException` for test helper in production run | Put `spring-security-test` in main sources or runtime | Only use helpers in `src/test/java` with test scope |
| Project calls `block()` in reactive handler | Logic blocking thread/event loop | Use Reactor operators, design appropriate reactive repositories/clients |
| Tests only cover happy paths | Missing coverage for unauthorized access | Add 401, 403, wrong password, right/wrong role, and non-owned resource tests |

### Post-creation self-check checklist

- [ ] Build selects **WebFlux** properly, without accidentally pulling in MVC/Servlet.
- [ ] Application runtime dependencies include `starter-webflux` and `starter-security`.
- [ ] Test dependencies include `starter-test` and `spring-security-test`, plus `reactor-test` if testing publishers.
- [ ] Spring Boot manages Spring Security and Reactor versions.
- [ ] There is a `SecurityWebFilterChain` with at least one `permitAll` rule and one rule requiring authorization.
- [ ] There are tests for **unauthenticated → 401**, **authorized → 200**, and **insufficient permissions → 403**.
- [ ] There are tests using **real credentials** and tests using **mock user**; you understand what each proves differently.
- [ ] `{noop}` or hardcoded passwords are not used in real environments.

## 9. Self-check questions

**Question 1.** If only `spring-boot-starter-webflux` is present without `spring-boot-starter-security`, does Spring WebFlux automatically enforce `hasRole`?  
**Answer:** No. WebFlux provides reactive HTTP handling, while authorization mechanisms belong to Spring Security.

**Question 2.** Why is `spring-security-test` placed in `test` scope?  
**Answer:** Because it provides simulation, setup, and security verification utilities for testing, not production user authentication components.

**Question 3.** Does a test using `mockUser("alice").roles("READER")` returning 200 prove Alice's password is correct?  
**Answer:** No. It proves the rule permits a mock principal with that role; a real test via HTTP Basic/identity provider is needed to verify the credential flow.

**Question 4.** Is it necessary to disable CSRF for GET `/api/reports` in the example to work?  
**Answer:** No. The lab only uses GET. CSRF is specifically a concern to check for state-changing requests, especially in applications authenticating with cookies/sessions.

**Question 5.** Why does a reactive application need `SecurityWebFilterChain` even though it is still Spring Security?  
**Answer:** Because WebFlux uses a reactive `WebFilter` chain and Reactor `Context`, which differs from Spring MVC's Servlet filter model.

## 10. Official documentation and key takeaways

- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security – Getting Started with WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/getting-started.html
- Spring Security – WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security – Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security – Testing with CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot – System Requirements (3.5): https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Initializr: https://start.spring.io/

**Takeaway:** `starter-webflux` builds the reactive web foundation; `starter-security` protects requests with a reactive security chain; `spring-security-test` works with `starter-test` to verify permissions and identity using `WebTestClient`. A properly configured project needs checks for both **runnability** and **200/401/403 behavior**, while distinguishing real authentication tests from mocked-user tests.
