# Role of `@EnableWebFluxSecurity` and Auto-Configuration in Spring Security Reactive

## 1. The big picture

In a **Spring WebFlux** application, Spring Security protects HTTP requests using `WebFilter`s operating with Reactor (`Mono`/`Flux`). Two concepts commonly encountered when bootstrapping an application are:

- **`@EnableWebFluxSecurity`**: a **Spring Security** annotation that enables the security configuration mechanism for WebFlux in the Spring application context.
- **Spring Boot auto-configuration**: inspects the application type, dependencies, and existing beans to automatically register default configuration. If a Boot app already has `spring-boot-starter-webflux` and `spring-boot-starter-security`, you normally **do not need to add `@EnableWebFluxSecurity` yourself** to get HTTP security.

Distinction to keep clear: *enabling security infrastructure*, *defining HTTP policies*, and *supplying authentication data* are three separate responsibilities. The annotation does not automatically make an endpoint public; adding a `SecurityWebFilterChain` does not automatically create a user store; adding a `ReactiveUserDetailsService` also does not decide which URLs are accessible.

Objectives after this lesson:
1. Explain the role of `@EnableWebFluxSecurity` and the automatic parts handled by Spring Boot.
2. Recognize the components `WebFilterChainProxy`, `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveUserDetailsService`.
3. Know when explicit configuration is required and what changes when each type of bean is added.
4. Run a Java 17+ application yourself and verify corresponding HTTP 200/401/403 responses.

## 2. What does `@EnableWebFluxSecurity` actually do?

`@EnableWebFluxSecurity` is usually placed on a `@Configuration` class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {
}
~~~

The annotation imports Spring Security configuration classes for WebFlux, thereby setting up request filtering infrastructure, security context management, and support for HTTP configuration beans. Without a custom `SecurityWebFilterChain`, Spring Security provides a typical default policy: requiring authentication for all requests, supporting form login and HTTP Basic, providing default login/logout pages when appropriate, and enabling CSRF protection and security headers.

What must **not** be inferred from the annotation alone:
- It is not a switch to "allow all requests".
- It is not synonymous with configuring users/passwords; in Spring Boot, that part is typically provided by `ReactiveUserDetailsServiceAutoConfiguration`.
- It does not replace `spring-boot-starter-security` or required libraries on the classpath.
- It does not enable method-level `@PreAuthorize` authorization; that requires separate **reactive method security** configuration, usually via `@EnableReactiveMethodSecurity`.
- It is not `@EnableWebSecurity`, which is meant for the **Servlet/Spring MVC** model.

In a **non-Spring Boot** application, declaring `@EnableWebFluxSecurity` is the explicit way to enable web security (along with the corresponding dependencies and beans). In a **Spring Boot WebFlux** application, auto-configuration usually already does the equivalent when conditions match.

## 3. At which layer does each object live?

~~~text
HTTP request
    │
    ▼
Spring WebFlux WebFilter infrastructure
    │
    ▼
Spring Security WebFilterChainProxy
    │  selects the security chain matching the request
    ▼
SecurityWebFilterChain
    ├─ authentication WebFilters (if mechanism is configured)
    ├─ security context / exception handling
    └─ URL authorization rules (AuthorizationWebFilter)
    │
    ▼
Controller / RouterFunction / Handler
~~~

- `WebFilterChainProxy` is part of the **reactive web filter** infrastructure; it connects Spring Security into the WebFlux processing pipeline.
- `SecurityWebFilterChain` is a set of filters and policies applying to a group of requests. Multiple chains can exist; Spring Security picks the matching chain in order.
- `ServerHttpSecurity` is the **builder** for declaring `authorizeExchange`, `httpBasic`, `formLogin`, `csrf`, `oauth2ResourceServer`, etc. Call `http.build()` to create a `SecurityWebFilterChain`.
- `ReactiveAuthenticationManager` verifies login credentials via a reactive interface; `ReactiveUserDetailsService` supplies users to matching authentication mechanisms. `ReactiveUserDetailsService` is a data source, not the entire authentication process.
- Spring Security reactive propagates `SecurityContext` through **Reactor Context**; do not rely on Servlet `ThreadLocal` assumptions to read identity across threads.

Comparing types with Spring MVC:

| WebFlux (reactive) | Servlet/MVC | Role |
| --- | --- | --- |
| `@EnableWebFluxSecurity` | `@EnableWebSecurity` | Enables security configuration for the respective web stack |
| `ServerHttpSecurity` | `HttpSecurity` | HTTP policy builder |
| `SecurityWebFilterChain` | `SecurityFilterChain` | Filter chain for HTTP requests |
| `WebFilterChainProxy` | `FilterChainProxy` | Security filter dispatcher |
| `ReactiveUserDetailsService` | `UserDetailsService` | User source |
| `ReactiveAuthenticationManager` | `AuthenticationManager` | Authentication handler |

APIs in the two columns cannot be arbitrarily substituted for one another. A WebFlux application with a Servlet `SecurityFilterChain(HttpSecurity)` configuration will not have the same effect as a reactive `SecurityWebFilterChain(ServerHttpSecurity)`.

## 4. What does Spring Boot auto-configure?

This section uses class names from **Spring Boot 3.3.x** (exact names or detailed conditions may vary in other Boot lines).

When the corresponding libraries are on the classpath and Spring Boot detects a **reactive web application**, the key configurations include:

- `ReactiveSecurityAutoConfiguration`: enables Spring Security infrastructure for WebFlux if no equivalent configuration is already present; depends on classpath/web application conditions and can yield to an already-defined `WebFilterChainProxy`.
- `ReactiveUserDetailsServiceAutoConfiguration`: if no suitable replacement authentication mechanism exists, creates a `ReactiveUserDetailsService` based on `spring.security.user.*` properties, typically an in-memory user.
- Spring Security WebFlux defaults: protects requests by default, supports form login/HTTP Basic, and enables other protections per framework defaults.

In a newly created app with the security starter, the default user is usually named **`user`** with a randomly generated password printed at startup (for development). Values can be changed via `spring.security.user.name` and `spring.security.user.password` when using the auto-configured user mechanism. This is not a login configuration for production.

### 4.1. What happens when we create custom beans?

| Change in a Boot WebFlux app | Result to understand |
| --- | --- |
| Add only WebFlux and Security starters | Boot configures default security, protects endpoints, creates test user if conditions match |
| Add `@EnableWebFluxSecurity` without defining a chain | Enables explicit configuration; **does not open endpoints automatically** |
| Create `@Bean SecurityWebFilterChain` | Uses the URL policy defined by that bean instead of the default HTTP chain; user authentication may still be created by Boot |
| Create `@Bean ReactiveUserDetailsService` | Uses custom user store, Boot does not need to create default user; HTTP access rules do not change automatically |
| Create `@Bean ReactiveAuthenticationManager` | Uses provided authentication mechanism; Boot's default user config may back off conditionally |
| Add `@EnableReactiveMethodSecurity` | Enables method-level security, complementing HTTP filter rules |

**Two different kinds of back-off:** Spring Boot 3.3 describes skipping the default web infrastructure registration when a `WebFilterChainProxy` already exists; meanwhile, a custom `SecurityWebFilterChain` replaces the default HTTP policy selected. These are two different bean levels. Creating a custom chain **does not mean** turning off all auto-configuration, especially the default user part.

In addition to beans, the presence of OAuth2 Client/Resource Server dependencies can change the default-user auto-configuration conditions. Therefore, when adding security starters/token providers, inspect the **actual beans** and auto-configuration conditions rather than assuming `user` always exists.

### 4.2. Misidentifying the web stack

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are added, Spring Boot usually prefers **Servlet/MVC**. The fact that an application uses `WebClient` does not prove it runs a WebFlux server. To build a reactive server, prefer `spring-boot-starter-webflux` and avoid accidentally pulling in the MVC starter. Only force `spring.main.web-application-type=reactive` when deliberately choosing reactive and understanding the accompanying dependencies.

## 5. Complete Java 17+ example with Spring Boot WebFlux

The example uses **Spring Boot 3.3.13**, Java 17+, Gradle 8.x; it uses GET endpoints only to focus on WebFlux security. Goal: permit `/public`, require login on `/private`, and require ADMIN permission on `/admin`.

### 5.1. Initializing the project

File structure:

~~~text
webflux-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── ReactiveSecurityDemoApplication.java
    │   ├── DemoController.java
    │   └── SecurityConfig.java
    └── test/java/demo/
        └── ReactiveSecurityDemoApplicationTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-security-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/ReactiveSecurityDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }
}
~~~

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/private")
    Mono<String> privateEndpoint() {
        return Mono.just("private");
    }

    @GetMapping("/admin")
    Mono<String> adminEndpoint() {
        return Mono.just("admin");
    }
}
~~~

**Observing auto-configuration before writing custom config:** temporarily **do not create `SecurityConfig.java`**. Run from the project directory:

~~~bash
gradle bootRun
~~~

If you have a Gradle Wrapper, use `./gradlew bootRun` on Unix/macOS or `gradlew.bat bootRun` on Windows. When the app starts, Spring Boot may print `Using generated security password: ...` (the value changes on each run). At this point **`/public` is still protected** because there is no `permitAll` rule yet. Unauthenticated API requests usually return HTTP 401 with HTTP Basic; browser requests accepting HTML may be redirected to the login page (302) due to content negotiation. You should not hardcode a random stdout/password for this step.

### 5.2. Defining a custom chain and user store

Add `src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {
        UserDetails demo = User.withUsername("demo")
            .password(passwordEncoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(demo);
    }
}
~~~

Read each component carefully:
1. `@EnableWebFluxSecurity` explicitly initializes Spring Security WebFlux configuration. In a Boot app with auto-configuration, this annotation is usually **not mandatory** but helps clearly show where infrastructure is enabled. You can remove it in this Boot example when auto-configuration conditions remain satisfied.
2. `@Bean SecurityWebFilterChain` **changes the access policy**. `/public` allows unauthenticated guests; `/admin` requires authority `ROLE_ADMIN` (`hasRole("ADMIN")` automatically prepends `ROLE_`); remaining paths require authentication.
3. `httpBasic(Customizer.withDefaults())` enables HTTP Basic; `formLogin(form -> form.disable())` removes form login so unauthenticated API results are easily observed as **401**. This is a **demo-specific choice**, not mandatory behavior of the annotation.
4. `MapReactiveUserDetailsService` replaces Boot's auto-generated user with a demo user. `BCryptPasswordEncoder` hashes the password; in practice users/passwords must come from secret configuration or a secure identity store, not hardcoded.
5. CSRF is not disabled in the example because only HTTP GET is used. With cookie/session-based POST/PUT/DELETE, CSRF is an important mechanism; if designing a stateless API that needs CSRF adjustments, evaluate a dedicated policy rather than copying an unconditional disable command.

After adding the class, stop and re-run `gradle bootRun`.

### 5.3. Checking via HTTP

The following commands are for bash/Git Bash, run on the machine hosting the server at `localhost:8080`:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/private
curl -s -u demo:demo-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/private
curl -s -u demo:demo-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin
~~~

When configured properly with no other filters interfering, stdout in order is:

~~~text
200
401
200
403
~~~

- **200**: `/public` has `permitAll`, requiring no identity.
- **401**: `/private` lacks credentials; HTTP Basic returns an authentication challenge.
- **200**: `demo` has the right password, satisfying `authenticated()`.
- **403**: `demo` is logged in but only has `ROLE_USER`, lacking `ROLE_ADMIN`.

For Windows PowerShell, you can use `curl.exe` and depending on the environment change the body discard target from `/dev/null` to `NUL`. If a browser redirected to `/login` during the default step, that was due to form login/content negotiation; after the demo configuration above, form login is disabled.

### 5.4. Automated testing with `WebTestClient`

`src/test/java/demo/ReactiveSecurityDemoApplicationTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveSecurityDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsOpen() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void privateRouteRequiresLogin() {
        client.get().uri("/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void loggedInUserCanAccessPrivateRoute() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("demo", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private");
    }

    @Test
    void ordinaryUserCannotAccessAdminRoute() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("demo", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Run `gradle test`; Gradle Wrapper can be used as above. When all checks pass, the command exits with code 0; do not predict Gradle logs verbatim since they vary by environment. `@SpringBootTest` verifies the context and security configuration together; `@WebFluxTest` only loads a slice of beans and usually needs `@Import` for custom security configurations if you want to test against your declared rules.

## 6. Comparing three common configuration approaches

### Approach A — Let Spring Boot handle all defaults

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

No need to write `@EnableWebFluxSecurity` or `SecurityWebFilterChain` yourself when the goal is simply to start up and observe the default mechanism. All routes are typically protected. Suitable for learning or quick bootstrapping, **not a production authentication design**.

### Approach B — Define HTTP policy, let Boot keep default auth

~~~java
@Configuration
class HttpRules {
    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/healthz").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

This is an **illustrative snippet**, requiring corresponding imports in the project. It creates a custom chain but **does not declare a `ReactiveUserDetailsService`**, so the default user can still be configured by Boot if conditions hold. This explains why even after "writing security config", the application still prints a random password.

### Approach C — Define both policy and authentication mechanism

The complete configuration in Section 5 handles both parts: `SecurityWebFilterChain` + `MapReactiveUserDetailsService`. For business applications, replace `MapReactiveUserDetailsService` with a reactive data source or Spring Security OAuth2 Resource Server to validate JWT/opaque tokens according to your chosen standard.

Do not write uncontrolled custom JWT parsers/password verifiers or turn a "user not found" case into a logged-in principal. All real authentication steps must propagate errors and results through reactive APIs according to contract.

## 7. When having multiple `SecurityWebFilterChain`s

An application may need separate policies for `/api/**` and remaining web pages. In that case, create chain beans with `@Order` and `securityMatcher(...)` to determine **which chain is selected** before applying the `authorizeExchange` rules inside.

Illustrative example (**configuration snippet, not a standalone Java program**):

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain otherChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Required imports include `org.springframework.core.annotation.Order`, `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher`, and the types used in Section 5. In this example, `otherChain` is a catch-all. If you only create a chain matching `/api/**` and omit a catch-all, requests outside that scope may not be protected by an application chain the way you expect. `pathMatchers` are access rules **inside a chain**, while `securityMatcher` is the condition for **selecting a chain**; these are two distinct concepts.

For simple needs, a single chain ending with `anyExchange().authenticated()` is easier to verify.

## 8. Misconceptions and how to diagnose them

| Symptom / misconception | Common cause | How to check |
| --- | --- | --- |
| "Added `@EnableWebFluxSecurity` yet all URLs still require login" | Annotation enables security, does not grant public access | Create a `SecurityWebFilterChain` with `permitAll` for routes that need to be open |
| "Created a chain yet a generated password still appears" | HTTP chain and user source are two different auto-configs | Provide a matching `ReactiveUserDetailsService` or `ReactiveAuthenticationManager` |
| "Configured `SecurityFilterChain(HttpSecurity)` yet WebFlux doesn't behave as expected" | Used Servlet API instead of reactive | Use `SecurityWebFilterChain(ServerHttpSecurity)` |
| "GET endpoint works, POST returns 403" | CSRF for state-changing requests or missing permission | Check CSRF token/authentication method and access rules |
| "`@WebFluxTest` doesn't use the application's rules" | Test slice doesn't automatically load custom security beans | Use `@Import` for the right config or `@SpringBootTest` |
| "Unexpectedly running Spring MVC" | Both Web MVC and WebFlux starters are present | Check dependencies and `WebApplicationType` |
| "User has ROLE_USER yet gets 403 on admin" | `hasRole("ADMIN")` requires authority `ROLE_ADMIN` | Check authority mapping and access policy |
| "Adding a custom chain unexpectedly exposed Actuator" | Did not specify matchers/rules for actuator endpoints | Check and separately test Actuator endpoints |
| "`@PreAuthorize` methods are not checked" | Reactive method security is not enabled | Enable `@EnableReactiveMethodSecurity` and test conditions |

### 8.1. Using the condition report to understand Boot's decisions

Spring Boot has an auto-configuration condition report. When you need to diagnose which beans were created or skipped, run:

~~~bash
gradle bootRun --args='--debug'
~~~

Read the **CONDITIONS EVALUATION REPORT** section and look for reactive security classes and reasons why conditions matched or did not match. The `--debug` flag makes logs longer; enable it only in development environments. Additionally, use bean listings or controlled observability tools to confirm whether `SecurityWebFilterChain`, `WebFilterChainProxy`, and `ReactiveUserDetailsService` are present. Do not expose management/diagnostic endpoints publicly just to debug.

### 8.2. Several safety principles

- **Deny by default** for resources not declared public; keep a tested catch-all rule.
- For Basic auth, HTTPS is mandatory in real life; local examples are for learning only.
- Do not put demo passwords, generated passwords, or tokens into production source or logs.
- Distinguish **401** (unauthenticated or invalid authentication) from **403** (authenticated but lacking permissions); exact HTTP statuses also depend on configured entry points, filters, and authentication mechanisms.
- If configuring Resource Server/JWT, validate issuer, audience, signature/expiration, and related claims using proper library components before accepting an identity.
- With multiple chains, test routes both inside and **outside** matchers, including actuator, error paths, and static resources if the app has them.

## 9. Self-check questions

1. **When using Spring Boot WebFlux with the security starter, is it mandatory to add `@EnableWebFluxSecurity`?** Usually no; auto-configuration already enables WebFlux security when conditions match.
2. **Does `@EnableWebFluxSecurity` automatically make `/public` freely accessible?** No. A `permitAll` rule in the chain is needed.
3. **Does creating a custom `SecurityWebFilterChain` automatically remove the default `user` account?** Not necessarily; user configuration has separate conditions.
4. **Which object is used to declare `pathMatchers`, `httpBasic`, and `formLogin`?** `ServerHttpSecurity`.
5. **Is `SecurityWebFilterChain` the same as `WebFilterChainProxy`?** No. A chain is a set of policies/filters; the proxy selects and executes the matching chain for a request.
6. **Which authority does `hasRole("ADMIN")` actually match under standard conventions?** `ROLE_ADMIN`.
7. **Is it correct to use `@EnableWebSecurity` to protect WebFlux handlers?** No; that is Servlet configuration.
8. **Which annotation is needed to enable `@PreAuthorize` in reactive method security?** `@EnableReactiveMethodSecurity` (with appropriate configuration).
9. **Why should full security tests prefer `@SpringBootTest` or importing custom config into slices?** Because test slices may not automatically load custom security chains.
10. **Why does `/admin` return 403 when called with the demo user?** The user is authenticated but lacks `ROLE_ADMIN`.

## 10. Official documentation

- Spring Boot 3.3 — Spring Security and WebFlux Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Boot 3.3 — `ReactiveSecurityAutoConfiguration`: https://docs.spring.io/spring-boot/3.3.13/api/java/org/springframework/boot/autoconfigure/security/reactive/ReactiveSecurityAutoConfiguration.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — `@EnableWebFluxSecurity` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/reactive/EnableWebFluxSecurity.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html

**Takeaway:** `@EnableWebFluxSecurity` is responsible for activating Spring Security's WebFlux configuration; Spring Boot typically registers infrastructure and a default user if conditions hold; the application-defined `SecurityWebFilterChain` is where the actual HTTP policy is expressed. Test policies **and** authentication sources as two separate parts.
