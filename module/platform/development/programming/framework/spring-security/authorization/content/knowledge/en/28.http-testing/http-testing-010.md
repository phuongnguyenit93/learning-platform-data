# Testing HTTP Authorization in Spring WebFlux: WebTestClient, mockUser, and authorizeExchange

## 1. Objectives and Scope

After this lesson, you can read an `authorizeExchange` configuration, determine which requests are allowed to proceed, write HTTP tests for unauthenticated guests and users with different roles/authorities, and recognize test failures caused by missing CSRF. The lesson focuses on **Spring Security on Spring WebFlux (reactive)**, where `ServerHttpSecurity` builds a `SecurityWebFilterChain` and `WebTestClient` simulates HTTP requests through the WebFlux processing chain.

Three components serve distinct responsibilities:

- `authorizeExchange(...)` declares **request authorization rules** (method, path, priority order).
- `mockUser(...)` in `SecurityMockServerConfigurers` attaches a simulated `Authentication` to the test request. It enables testing authorization without performing a real login.
- `WebTestClient` sends test requests and asserts HTTP status, headers, and body. When bound to `ApplicationContext` and integrated with Spring Security, requests pass through the application's security filters.

**Stack distinction:** This is the reactive `ServerHttpSecurity.authorizeExchange` DSL, returning `SecurityWebFilterChain`. Spring MVC/Servlet applications normally use `HttpSecurity.authorizeHttpRequests`, `SecurityFilterChain`, and `MockMvc`; do not copy WebFlux configuration verbatim to Servlet.

## 2. How Requests Flow Through Security

Overview flow:

1. `WebTestClient` creates a GET/POST request with URI, headers, and optional body.
2. Spring Security's `WebFilter` chain handles security concerns, including authentication, CSRF protection, and authorization.
3. `authorizeExchange` selects a matching rule in **declaration order**: the first matching rule takes effect.
4. Only when allowed does the request reach the WebFlux handler/controller; `WebTestClient` then inspects status and response body.

Authentication answers "who is the caller?"; authorization answers "what may that caller do?". `mockUser("mai").roles("ADMIN")` creates an authenticated user in the test environment with authority `ROLE_ADMIN`. It **does not** verify passwords, JWTs, session cookies, or real login flows.

Commonly used rules:

| Configuration | Meaning |
| --- | --- |
| `.pathMatchers("/public/**").permitAll()` | Unauthenticated guests may access |
| `.pathMatchers("/admin/**").hasRole("ADMIN")` | Requires authority `ROLE_ADMIN`; do not pass `ROLE_ADMIN` into `hasRole` |
| `.pathMatchers("/report/**").hasAuthority("report:read")` | Requires exact authority string `report:read` |
| `.pathMatchers(HttpMethod.POST, "/report").hasAuthority("report:write")` | Applies only to POST at that path |
| `.anyExchange().authenticated()` | All unmatched requests must be authenticated |
| `.anyExchange().denyAll()` | Denies unmatched requests by default |

`hasRole("ADMIN")` differs from `hasAuthority("ADMIN")`: with the default role prefix, the former checks `ROLE_ADMIN` while the latter checks exact `ADMIN`. Using `roles("ADMIN")` in mocks produces `ROLE_ADMIN`; using `authorities("report:write")` produces an arbitrary permission.

**Place specific rules before broad rules.** For example, if `.pathMatchers("/api/**").authenticated()` precedes `.pathMatchers("/api/admin/**").hasRole("ADMIN")`, admin paths match the first rule and the trailing role rule has no effect. Put `.anyExchange()` at the end of the chain.

## 3. Building a Runnable Example (Java 17, Spring Boot 3.5.7)

The sample project uses Maven and only WebFlux, without the Spring MVC starter. The files below form **the complete example code** in package `com.example.authz`.

Layout:

```text
webflux-authz/
├── pom.xml
└── src/
    ├── main/java/com/example/authz/
    │   ├── DemoApplication.java
    │   ├── ApiController.java
    │   └── SecurityConfig.java
    └── test/java/com/example/authz/
        └── ApiSecurityTests.java
```

### 3.1. Maven Configuration

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-authz</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

`spring-security-test` provides `mockUser`, `csrf`, and `springSecurity()`; `spring-boot-starter-test` provides JUnit 5 and Spring Test; `spring-boot-starter-webflux` provides WebFlux and the `WebTestClient` API via test dependencies.

### 3.2. Application and Endpoints

`src/main/java/com/example/authz/DemoApplication.java`:

```java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/com/example/authz/ApiController.java`:

```java
package com.example.authz;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {
    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    public Mono<String> profile() {
        return Mono.just("profile");
    }

    @GetMapping("/admin/report")
    public Mono<String> readReport() {
        return Mono.just("report");
    }

    @PostMapping("/admin/report")
    public Mono<String> createReport() {
        return Mono.just("created");
    }
}
```

Handlers return `Mono<String>` to illustrate a reactive app. Returned bodies are constants so status evaluation depends directly on security configuration.

### 3.3. authorizeExchange Configuration

`src/main/java/com/example/authz/SecurityConfig.java`:

```java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/report").hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/admin/report").hasAuthority("report:write")
                .pathMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Explanation of each path:

- `GET /api/public`: open to everyone, including unauthenticated callers.
- `GET /api/profile`: requires login; specific role does not matter.
- `GET /api/admin/report`: requires `ROLE_ADMIN`.
- `POST /api/admin/report`: requires authority `report:write` **and** a valid CSRF token because the example leaves CSRF enabled by default.
- Other methods/paths: `.anyExchange().denyAll()` (never accidentally expose new endpoints).
- `httpBasic` enables HTTP Basic challenge responses for unauthenticated requests; in tests, `mockUser` bypasses sending Basic credentials.

Here `.pathMatchers(HttpMethod.GET, ...)` and `.pathMatchers(HttpMethod.POST, ...)` separate two permissions on the same URL. These rules evaluate HTTP requests, not data ownership of a database record.

## 4. Testing with WebTestClient + mockUser

`src/test/java/com/example/authz/ApiSecurityTests.java`:

```java
package com.example.authz;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ApiSecurityTests {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

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
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void profileRequiresAuthentication() {
        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCanReadProfile() {
        client.mutateWith(mockUser("mai").roles("USER"))
            .get().uri("/api/profile")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile");
    }

    @Test
    void regularUserCannotReadAdminReport() {
        client.mutateWith(mockUser("mai").roles("USER"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadReport() {
        client.mutateWith(mockUser("lan").roles("ADMIN"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report");
    }

    @Test
    void writerCanCreateReportWithCsrfToken() {
        client.mutateWith(mockUser("linh").authorities("report:write"))
            .mutateWith(csrf())
            .post().uri("/api/admin/report")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void missingCsrfTokenBlocksPostEvenForWriter() {
        client.mutateWith(mockUser("linh").authorities("report:write"))
            .post().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleAloneDoesNotGrantWriteAuthority() {
        client.mutateWith(mockUser("lan").roles("ADMIN"))
            .mutateWith(csrf())
            .post().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run in the folder containing `pom.xml`:

```bash
mvn test
```

**Expected outcome:** all eight JUnit tests pass (Maven exits with code 0). The tests do not open a real HTTP port: `bindToApplicationContext(context)` routes requests through WebFlux handlers and security filters in `ApplicationContext`; `.apply(springSecurity())` installs the security test support needed for `mockUser`/`csrf`.

Reading an assertion chain:

- `.get()` or `.post()` picks the HTTP method; `.uri(...)` picks the path.
- `.mutateWith(mockUser(...))` creates a client mutator for a simulated authenticated user on the request.
- `.exchange()` executes the request against the mock server.
- `.expectStatus()` checks status; `.expectBody(String.class).isEqualTo(...)` checks body content only when the request is allowed to reach the controller.
- `.mutateWith(csrf())` supplies a valid CSRF token for POST testing without granting extra roles/authorities.

`mockUser()` defaults to username `user` and role `USER`; `mockUser("lan").roles("ADMIN")` uses authority `ROLE_ADMIN`. `authorities("report:write")` does not prepend `ROLE_`. Thus, the ADMIN role in the lesson does not imply `report:write`; the final test proves the two conditions are independent.

## 5. Matrix of Cases to Protect

| Request | Authentication and permission state | CSRF | Expected status | Reason |
| --- | --- | --- | --- | --- |
| GET `/api/public` | Anonymous guest | Not needed | `200` | `permitAll()` |
| GET `/api/profile` | Anonymous guest | Not needed | `401` | `authenticated()` and HTTP Basic |
| GET `/api/profile` | `ROLE_USER` | Not needed | `200` | Authenticated |
| GET `/api/admin/report` | `ROLE_USER` | Not needed | `403` | Lacks `ROLE_ADMIN` |
| GET `/api/admin/report` | `ROLE_ADMIN` | Not needed | `200` | Right role |
| POST `/api/admin/report` | `report:write` | Present | `200` | Right authority, valid CSRF |
| POST `/api/admin/report` | `report:write` | Absent | `403` | Blocked by CSRF protection layer |
| POST `/api/admin/report` | Only `ROLE_ADMIN` | Present | `403` | Lacks authority `report:write` |

Normally `401 Unauthorized` indicates **unauthenticated** and `403 Forbidden` indicates **authenticated but denied**, though actual status also depends on entry point mechanisms, CSRF, filter ordering, and app config. Never assert that every 403 is due to a missing role. To test a POST authorization rule in isolation, supply a valid CSRF token first.

Try adding negative cases when rules change:

- If you swap `hasRole("ADMIN")` and `authenticated()` for the same path, the `ROLE_USER` test can flip from 403 to 200; negative tests catch permission leaks.
- If you replace `hasAuthority("report:write")` with `hasRole("ADMIN")`, the previous writer test turns 403 and the admin-with-CSRF test can turn 200.
- If you add a new endpoint while keeping `.anyExchange().denyAll()`, declare a new intentional rule and test both allowed and denied cases.

## 6. When to Use @WithMockUser, WebFluxTest, or Live HTTP Tests?

`@WithMockUser` is another way to set the security context for Spring Security integration tests; when varying identity per request, `client.mutateWith(mockUser(...))` makes each case clearer. Illustrative example (placed in a test class wired with Spring Security and `import org.springframework.security.test.context.support.WithMockUser`):

```java
@WithMockUser(roles = "ADMIN")
@Test
void adminUsingAnnotation() {
    client.get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk();
}
```

For a standalone WebFlux controller, you can use `@WebFluxTest(ApiController.class)` and `@Import(SecurityConfig.class)`; slice tests do not automatically scan custom `SecurityWebFilterChain` beans, so the security configuration must be imported. The main example uses `@SpringBootTest` to ensure the app's exact filter chain is tested. When you do not need to build the client manually, Spring Boot also offers `@AutoConfigureWebTestClient` to inject `WebTestClient` in a mock web environment.

`mockUser` only proves **allow/deny logic with a simulated Authentication**. To verify real login, HTTP Basic credentials, JWT validation, OAuth2, sessions/cookies, or reverse proxies, write corresponding integration tests with the real authentication mechanism. For tests sending HTTP to a live server (`bindToServer()`/random port), use real credentials/tokens or appropriate test fixtures; do not rely on `mockUser` to simulate remote server-side authentication.

## 7. Common Mistakes and Diagnosis

1. **Every request returns 200 despite declared security.** You may have bound the client directly to the controller via `bindToController(...)` without attaching the real security chain, or a slice test lacked `@Import(SecurityConfig.class)`. Confirm the test loads `SecurityWebFilterChain`.
2. **`mockUser` has no effect or context is missing.** Check the `spring-security-test` dependency, calling `springSecurity()` when manually binding to `ApplicationContext`, and importing WebFlux's `SecurityMockServerConfigurers.mockUser` (not the Servlet request post-processor).
3. **Has `ADMIN` yet still gets 403.** Check whether `.hasRole("ADMIN")` expects `ROLE_ADMIN`; check whether the request is actually GET or POST; if POST, check CSRF and separate authorities.
4. **Placed `.anyExchange()` or a broad matcher too early.** Subsequent rules are never evaluated once an earlier matcher matches; add negative tests for sensitive endpoints.
5. **Concluding 401/403 means 404.** Security filters can block requests before WebFlux looks up handlers, so non-existent endpoints can still receive 401/403 depending on rules. To verify mappings, inspect URIs and authorization config independently.
6. **Tests pass yet production leaks permissions.** Mocks only show the code picks the right rule for a fake principal. Also test role mapping from tokens/identity providers, multiple `SecurityWebFilterChain`s, per-resource permissions, and service-layer guards if required.
7. **Disabling CSRF just to make POST tests pass.** This alters the application's security behavior. Keep CSRF aligned with real configuration; when testing POST, add `.mutateWith(csrf())`. Disable CSRF only when the API's architecture and authentication model clearly justify it.

## 8. Self-Assessment Checklist

Before considering an authorization test suite sufficient, ensure you can answer:

- Is the configuration using WebFlux `authorizeExchange` or Servlet `authorizeHttpRequests`?
- For each endpoint, which HTTP method, path, and **first** matcher applies?
- Do tests cover anonymous guests, authorized users, unauthorized users, and nearly matching but non-identical permissions?
- Is the difference between `roles("ADMIN")` and `authorities("report:write")` clear?
- Do POST/PUT/PATCH/DELETE tests reflect the application's CSRF policy?
- Do requests traverse the real filter chain or only invoke the controller?
- Does the real authentication mechanism (passwords, tokens, sessions) have its own test suite?

Mastering three points — **clear rules, accurate permission mocks, and testing blocked cases** — helps catch HTTP authorization bugs early without spinning up a server for every case.

## Official Documentation

- Spring Security, Reactive HTTP authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security, WebTestClient test setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security, testing authentication with `mockUser`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security, testing CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot 3.5, testing WebFlux controllers and `@WebFluxTest`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html