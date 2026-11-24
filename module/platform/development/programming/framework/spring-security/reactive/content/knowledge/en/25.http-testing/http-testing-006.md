# Testing HTTP Basic with Valid and Invalid Credentials in Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Knowledge group:** HTTP Testing  
> **Lesson:** Testing HTTP Basic with Valid and Invalid Credentials  
> **Goal:** Write and understand WebFlux tests that prove HTTP Basic authenticates **real usernames/passwords**, distinguish 401 and 403 errors, check `WWW-Authenticate`, avoid bypassing security filters when using mocks, protect state-changing endpoints with CSRF, and build a JUnit 5 + `WebTestClient` suite covering success and failure cases.

## 1. Problem: test the real authentication path, not just mocked login

The application provides these endpoints:

- `GET /public/ping`: public.
- `GET /api/me`: requires an authenticated user.
- `GET /api/reports`: allowed for role ANALYST or ADMIN.
- `GET /api/admin`: ADMIN role only.
- `POST /api/reports`: ANALYST only and must satisfy CSRF when protecting this endpoint with Basic for browsers.

The application has no form login, does not accept JWTs in this example, and does not rely on HTTP sessions to store Authentication. Every request to a private endpoint needs valid HTTP Basic credentials, unless another policy is explicitly declared.

The test suite must prove **three distinct things**:

1. **Authentication:** passwords are actually verified against BCrypt hashes from a `ReactiveUserDetailsService`. Valid username + valid password → passes. Valid username + wrong password → 401.
2. **Authorization:** an authenticated account lacking the required route privilege → 403, not a password failure.
3. **Protocol security:** missing or invalid `Authorization` headers → 401; Base64-encoded passwords are **not** secure encryption; Basic challenges are returned when required; and CSRF protects state-changing requests if browsers may auto-send credentials.

Important: `mockUser()` or `@WithMockUser` **does not prove** HTTP Basic password verification ran. They pre-populate an Authentication into the test context, which is useful for testing authorization but does not replace testing real Basic headers.

## 2. How does HTTP Basic work?

Per RFC 7617, the client sends credentials in the form:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Basic YW5hbHlzdDpsYWItcGFzcy0xMjM=
Accept: application/json
~~~

The Base64 string in the example encodes `analyst:lab-pass-123`. This is a public dummy password used solely in the lab.

Flow:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant W as WebFlux SecurityWebFilterChain
    participant B as HTTP Basic authentication converter
    participant M as ReactiveAuthenticationManager
    participant U as ReactiveUserDetailsService
    participant H as Controller
    C->>W: GET /api/me + Authorization Basic ...
    W->>B: Parse scheme + Base64(username:password)
    B->>M: UsernamePasswordAuthenticationToken (unauthenticated)
    M->>U: findByUsername(username)
    U-->>M: UserDetails + BCrypt password hash
    M->>M: PasswordEncoder.matches(raw, storedHash)
    alt Incorrect or missing credential
        M-->>C: 401 + Basic challenge (per entry point)
    else Credential valid
        M->>W: Authenticated principal + authorities
        W->>W: authorizeExchange route rule
        alt Missing required authority
            W-->>C: 403 Forbidden
        else Authorized
            W->>H: Invoke endpoint
            H-->>C: 200 JSON
        end
    end
~~~

**Base64 != Encryption:** anyone who can read plaintext traffic can Base64-decode the username/password. Never use Basic over internet HTTP; use HTTPS with verified certificates only. Never embed credentials in URLs or repositories, and never log the Authorization header. HTTP/2, TLS termination, and reverse proxies must still protect the path to the server.

**Colon delimiter:** Basic is built from the `username:password` string, split at the first `:`. Usernames must not contain `:`; passwords **may** contain `:`. Character encoding in Basic has interoperability considerations; to keep test examples predictable, use ASCII usernames/passwords and verify server UTF-8/charset policies if international characters are needed.

## 3. Distinguishing 401 Unauthorized and 403 Forbidden

| Scenario | Authentication | Authorization | Expected result |
| --- | --- | --- | --- |
| `GET /public/ping` no credentials | Not required | Public route | **200** |
| `GET /api/me` no header | Unauthenticated | Auth required | **401** |
| Valid username, wrong password | Failed | Permissions not evaluated | **401** |
| Non-existent username | Failed | Permissions not evaluated | **401** |
| Malformed Base64 / wrong scheme | No valid Basic credential | Auth required | **401** |
| analyst + valid password on `/api/me` | Succeeded | Auth only | **200** |
| analyst + valid password on `/api/admin` | Succeeded | Missing ADMIN | **403** |
| admin + valid password on `/api/admin` | Succeeded | Has ADMIN | **200** |
| analyst + valid password + POST without CSRF | Succeeded | Invalid CSRF | **403** |
| analyst + valid password + POST with valid CSRF | Succeeded | Has ANALYST + CSRF | **201** |

**A 401 response must not reveal the exact reason an account was rejected.** Avoid returning "username not found" for unknown users vs "password incorrect" for wrong passwords; keep errors generic so they do not facilitate account enumeration. Safe error codes may be recorded in internal logs, never raw credentials.

**403 is not "login failed":** if the caller is already authenticated but lacks an authority, resending the same password normally will not help. It is a permission issue at the route or domain layer.

## 4. The `WWW-Authenticate` header and reading test results

When a private request is unauthenticated, the HTTP Basic entry point typically sends:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
~~~

This is an **illustrative format**; the exact realm name and response headers depend on the Spring Security version/configuration and proxy. Tests should verify that the header starts with `Basic` when the route requires a challenge, rather than hardcoding every byte of the realm.

Per entry-point policy, special requests such as XHR or API gateways may alter the challenge, so do not force every 401 response to have the exact same body/headers if the application configures custom exception handling.

Headers must never contain usernames/passwords, BCrypt hashes, or hints like "this account exists". A Basic challenge can cause browsers to pop up a login dialog; in SPA/API-first apps, some teams intentionally customize the entry point to control UX, and must test that decision separately.

## 5. Which testing approach to choose?

| Approach | Data sent | What does it prove? | Limitations |
| --- | --- | --- | --- |
| `WebTestClient.headers(h -> h.setBasicAuth(...))` | Real HTTP Basic header | Basic converter + manager + BCrypt + route | When bound in-memory, does not test TCP/TLS/proxy |
| `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` | Mock HTTP request, real filter chain | End-to-end WebFlux security inside ApplicationContext | Does not open a Netty socket |
| `@SpringBootTest(RANDOM_PORT)` + WebTestClient | HTTP request to real Netty server | HTTP network + filters + password lookup | Slower; still does not prove internet TLS |
| `mockUser("alice")` | Attaches fake Authentication | Route role/authority logic | **Does not verify Basic password** |
| `@WithMockUser` | Creates mock SecurityContext | Method security annotations and authorization | **Does not verify Base64 header** |
| `@WebFluxTest` | Web slice | Controller/security when right chain is imported | Can omit custom SecurityWebFilterChain if import is forgotten |
| `curl --user ...` | Basic header over network | Smoke test against running environment | Risks exposing password in terminal/history if misused |

**Choose at least two layers for this lesson:** in-memory `WebTestClient` with the real Spring Security filter chain for thorough case coverage, plus a few `RANDOM_PORT` smoke tests to verify real Netty HTTP.

Do not use `MockMvc` as the primary tool for Spring WebFlux. It is for Servlet MVC; if a project has both `spring-boot-starter-web` and WebFlux, Boot usually prioritizes MVC unless reactive mode is explicitly configured.

## 6. Spring Security Reactive architecture for Basic

Server-side components include:

- `SecurityWebFilterChain`: the set of security WebFilters for WebFlux HTTP.
- `ServerHttpSecurity`: the DSL configuring `httpBasic`, authorization, and CSRF.
- `ServerHttpBasicAuthenticationConverter`: converts a Basic header into an unauthenticated `UsernamePasswordAuthenticationToken`.
- `ReactiveAuthenticationManager`: verifies credentials; may use `UserDetailsRepositoryReactiveAuthenticationManager` or a custom provider.
- `ReactiveUserDetailsService`: loads user/password hash/roles; the demo uses `MapReactiveUserDetailsService`.
- `PasswordEncoder`: compares raw passwords against hashes; the demo uses `BCryptPasswordEncoder`.
- `ServerAuthenticationEntryPoint`: initiates the 401/challenge response mechanism.
- `ReactiveAuthorizationManager`: evaluates `authenticated`/`hasRole`/`hasAuthority` rules.
- `ReactiveSecurityContextHolder`: security context backed by Reactor rather than a single-thread `ThreadLocal`.

In the lab, `NoOpServerSecurityContextRepository` is used so Authentication is **not persisted** across HTTP sessions. This does not mean WebFlux as a whole cannot use WebSession: the CSRF token repository or other components may still use sessions if configured.

HTTP Basic is a **per-request credential**. Do not confuse Basic with authenticating once and creating a login session cookie. When using browsers, the browser may cache Basic credentials and resend them automatically, so not persisting `SecurityContext` does **not** automatically eliminate CSRF risk.

## 7. Security requirements for the lab

1. **Secure by default:** unlisted routes are denied.
2. Only `GET /public/ping` requires no auth.
3. `GET /api/me` requires an authenticated principal.
4. `GET /api/reports` requires role ANALYST **or** ADMIN.
5. `GET /api/admin` requires role ADMIN.
6. `POST /api/reports` requires role ANALYST and a valid CSRF token (to illustrate browser Basic).
7. No formLogin, no requestCache, no persisting SecurityContext in WebSession.
8. Passwords for the three lab users are supplied via configuration and BCrypt-hashed at startup.
9. No default accounts/passwords declared for use outside tests.
10. Tests send **real** Basic headers rather than using `mockUser` to skip password checks.
11. With Spring Security's default entry point, missing/wrong Basic returns 401; authenticated lacking scope/role returns 403.
12. For production, replace in-memory users with a backing store and add brute-force protection, MFA/vault/monitoring appropriate to the environment.

## 8. Java 17+ / Maven project

The example pins parent `Spring Boot 3.5.16`, on the 3.x line using Spring Security 6.x. This is a **baseline version for reading the code**, not a claim that it is the latest patched release when you study; production must check supported versions, CVEs, and apply appropriate patches.

~~~text
webflux-http-basic-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/basic/
    │   │   ├── BasicApplication.java
    │   │   ├── BasicSecurityConfig.java
    │   │   └── AccountController.java
    │   └── resources/application.yml
    └── test/java/demo/basic/
        ├── BasicFilterTest.java
        └── BasicNetworkTest.java
~~~

**Why two test classes?** `BasicFilterTest` uses `WebTestClient` bound directly to the WebFlux context, making it fast to exercise many cases. `BasicNetworkTest` starts Netty on a random TCP port to prove real HTTP traffic flows through the Basic filter; neither uses `mockUser`.

### 8.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>webflux-http-basic-tests</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
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
~~~

`spring-boot-starter-web`, Spring Session, or JWT starters are not needed; the lesson focuses on Basic and WebFlux. `spring-security-test` provides `springSecurity()` and `csrf()` for `WebTestClient`. `reactor-test` is not required for these HTTP response tests; if adding direct `Mono`/`Flux` tests, declare it separately.

### 8.2. `BasicApplication.java`

~~~java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicApplication.class, args);
    }
}
~~~

### 8.3. `application.yml`

~~~yaml
server:
  port: 8080

lab:
  users:
    analyst-password: "${LAB_ANALYST_PASSWORD:}"
    admin-password: "${LAB_ADMIN_PASSWORD:}"
    colon-password: "${LAB_COLON_PASSWORD:}"
~~~

Without configured passwords, the app must **fail fast**. The code creates no default users/passwords outside tests, preventing accidental public deployment with credentials published in a tutorial.

In production, use a secret store/vault and IAM rather than placing cleartext passwords in Git, build logs, or unencrypted CI configs. For larger user sets, use a database or identity provider instead of in-memory `MapReactiveUserDetailsService`.

## 9. `BasicSecurityConfig.java` — HTTP Basic + BCrypt + roles + CSRF

File `src/main/java/demo/basic/BasicSecurityConfig.java`:

~~~java
package demo.basic;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class BasicSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${lab.users.analyst-password:}") String analystPassword,
            @Value("${lab.users.admin-password:}") String adminPassword,
            @Value("${lab.users.colon-password:}") String colonPassword) {

        if (analystPassword.isBlank()
                || adminPassword.isBlank()
                || colonPassword.isBlank()) {
            throw new IllegalStateException(
                "Configure all LAB_*_PASSWORD secrets");
        }

        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode(analystPassword))
            .roles("ANALYST")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(adminPassword))
            .roles("ADMIN")
            .build();

        UserDetails colon = User.withUsername("colon")
            .password(encoder.encode(colonPassword))
            .roles("ANALYST")
            .build();

        return new MapReactiveUserDetailsService(
            analyst, admin, colon);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAnyRole("ANALYST", "ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("ANALYST")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            // Do not disable CSRF: Basic credentials can be auto-sent by browsers.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

**Detailed explanation:**

- `@EnableWebFluxSecurity` activates reactive security, and `SecurityWebFilterChain` applies the HTTP rules.
- `MapReactiveUserDetailsService` is a **demo** user store; `BCryptPasswordEncoder(12)` stores bcrypt hashes rather than comparing raw strings.
- The three users receive credentials from secrets/config; tests will inject dummy passwords via `@SpringBootTest(properties=...)`.
- `roles("ADMIN")` creates `ROLE_ADMIN`; `hasRole("ADMIN")` checks the proper authority prefix. `hasAnyRole("ANALYST","ADMIN")` allows either role; POST allows only ANALYST so we have an independent 403 test.
- `httpBasic(Customizer.withDefaults())` registers the Basic authentication converter/manager and entry point.
- `formLogin(...disable)` disables the form login page; this API relies on Basic.
- `NoOpServerSecurityContextRepository` avoids saving Authentication across `WebSession`; each Basic request needs credentials rather than relying on prior login state.
- `requestCache(...disable)` avoids keeping login-flow request caching.
- `csrf(Customizer.withDefaults())` preserves CSRF protection for state-changing requests: a POST with a valid password but missing CSRF still gets 403. The CSRF token repository may still create a `WebSession`, which does not conflict with `NoOpServerSecurityContextRepository`.
- `anyExchange().denyAll()` prevents new routes from accidentally becoming public.

**Note:** Username/password authentication sometimes goes through a custom `ReactiveAuthenticationManager` or multiple providers; if the real app uses LDAP/DB/IdP, test the actual production provider rather than swapping in `MapReactiveUserDetailsService` and assuming password policies were verified. Spring Security WebFlux does not automatically protect tenant/object data based on roles alone.

## 10. `AccountController.java` — simple endpoints, never returning passwords

File `src/main/java/demo/basic/AccountController.java`:

~~~java
package demo.basic;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AccountController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "up"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal UserDetails principal) {
        return Mono.just(Map.of(
            "username", principal.getUsername()));
    }

    @GetMapping("/api/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of("report", "readable"));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("section", "admin"));
    }

    @PostMapping("/api/reports")
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Map<String, String>> createReport() {
        return Mono.just(Map.of("status", "created"));
    }
}
~~~

**Why doesn't the controller parse headers manually?** Authentication must be handled by Spring Security first: the controller only reads the authenticated `@AuthenticationPrincipal UserDetails`. Manually calling `Base64.decode`, comparing passwords, and authorizing inside controllers risks leaving other routes unprotected and loses centralized security semantics.

The JSON bodies are illustrative only; production must never return passwords, BCrypt hashes, `Authorization` headers, or secrets. `createReport` does not actually persist a report; status 201 enables route/CSRF testing without side effects.

## 11. Guide to building a genuinely protected WebTestClient

The first test class binds `WebTestClient` to the `ApplicationContext`:

~~~java
client = WebTestClient.bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

**Why not use `bindToController(new AccountController())` alone?** Binding only the controller without providing the security filter chain lets tests call protected endpoints and receive 200, which is **not** a security test. `bindToApplicationContext(...)` picks up the WebFlux infrastructure and `springSecurity()` applies `SecurityWebFilterChain`, enabling the credential converter, authentication manager, and authorization to run.

To send real Basic credentials:

~~~java
client.get().uri("/api/me")
    .headers(headers ->
        headers.setBasicAuth("analyst", "lab-pass-123"))
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.username").isEqualTo("analyst");
~~~

Spring's `headers.setBasicAuth(username,password)` constructs a properly formatted `Authorization: Basic ...` header, avoiding manual Base64 encoding for positive cases. Only craft raw headers manually for negative tests.

Do not use `.mutateWith(mockUser("analyst"))` in **password-verification tests**, because that request bypasses the Basic converter/BCrypt authentication flow; it injects a pre-trusted mock Authentication in tests.

## 12. `BasicFilterTest.java` — positive and negative authentication

File `src/test/java/demo/basic/BasicFilterTest.java`. In the test properties, all passwords are **dummy test credentials** and must never be used in production.

~~~java
package demo.basic;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(properties = {
    "lab.users.analyst-password=lab-pass-123",
    "lab.users.admin-password=admin-pass-456",
    "lab.users.colon-password=pa:ss"
})
class BasicFilterTest {

    private static final String ANALYST = "analyst";
    private static final String GOOD = "lab-pass-123";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private String rawBasic(String decoded) {
        return "Basic " + Base64.getEncoder().encodeToString(
            decoded.getBytes(StandardCharsets.ISO_8859_1));
    }

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("up");
    }

    @Test
    void missingCredentialsAreUnauthorized() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void correctAnalystCredentialsAreAccepted() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("analyst")
            .jsonPath("$.password").doesNotExist();
    }

    @Test
    void correctAdminCredentialsAreAccepted() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-pass-456"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("admin");
    }

    @Test
    void wrongPasswordIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                ANALYST, "incorrect-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "not-a-user", GOOD))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void emptyPasswordIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                ANALYST, ""))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedBase64IsUnauthorized() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION,
                "Basic !!!not-base64!!!")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void decodedBasicWithoutColonIsUnauthorized() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION,
                rawBasic("analyst"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void bearerSchemeIsNotAcceptedAsBasic() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer not-an-access-token")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void emptyAuthorizationHeaderIsUnauthorized() {
        client.get().uri("/api/me")
            .header(HttpHeaders.AUTHORIZATION, "")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void colonInsidePasswordIsSupported() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("colon", "pa:ss"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("colon");
    }

    @Test
    void analystCanReadReports() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("readable");
    }

    @Test
    void adminCanReadReports() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-pass-456"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void analystCannotAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminMayAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-pass-456"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.section").isEqualTo("admin");
    }

    @Test
    void anonymousAdminRequestIsUnauthorized() {
        client.get().uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicChallengeIsOfferedWhenMissing() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "^Basic.*");
    }

    @Test
    void validBasicWithoutCsrfStillCannotPost() {
        client.post().uri("/api/reports")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validBasicAndCsrfCanPost() {
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.status").isEqualTo("created");
    }

    @Test
    void wrongBasicStillFailsEvenWithCsrf() {
        client.mutateWith(csrf())
            .post().uri("/api/reports")
            .headers(h -> h.setBasicAuth(
                ANALYST, "incorrect-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void nextRequestDoesNotInheritPriorBasicIdentity() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(ANALYST, GOOD))
            .exchange()
            .expectStatus().isOk();

        // Second request has no Authorization header.
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

**22 tests** against the same Spring ApplicationContext using `WebTestClient` with **real Basic headers** to exercise the authentication chain. This verifies WebFlux filters and BCrypt, though it does not open a TCP socket or test TLS proxies.

**Why include multiple negative test shapes?** If you only test one "wrong password" case, the app might still accept a Bearer token by mistake, accept malformed Base64, miss a route role, or pass everything via `mockUser`. Each test guards a specific pipeline decision.

**Expected output:** test methods produce no fixed business stdout; Maven Surefire/JUnit displays test counts and PASS/FAIL depending on the environment. Do not compare 401 error bodies byte-for-byte since Spring Boot can configure different error handlers.

## 13. Why send real Basic headers instead of `mockUser`?

The following test **does not verify passwords**:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("analyst").roles("ANALYST"))
    .get().uri("/api/reports")
    .exchange().expectStatus().isOk();
~~~

Even if the database has no `analyst` user or the password changed, the mock can still supply an Authentication with test-provided roles. That is an **authorization test**. It is valuable for checking route/method-level rules, but does not replace this lesson's test suite.

Conversely, with:

~~~java
client.get().uri("/api/me")
    .headers(h -> h.setBasicAuth("analyst", "incorrect-password"))
    .exchange().expectStatus().isUnauthorized();
~~~

Spring Security must parse Base64, look up the user, compare the BCrypt hash, and reject the wrong password. If a test pre-populates an authenticated `Authentication` and also sends a Basic header, the mock principal can interfere with the outcome and fail to prove Basic works.

**Anti-pattern:** putting `@WithMockUser` at the class level on the very tests meant for "invalid password", causing requests to be authenticated before the header is evaluated. Keep Basic-credential test classes separate from pure authorization-mock test classes.

## 14. `BasicNetworkTest.java` — verifying HTTP over real Netty

In addition to in-memory tests, add a small group running the server on a random port:

File `src/test/java/demo/basic/BasicNetworkTest.java`:

~~~java
package demo.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "lab.users.analyst-password=lab-pass-123",
        "lab.users.admin-password=admin-pass-456",
        "lab.users.colon-password=pa:ss"
    }
)
@AutoConfigureWebTestClient
class BasicNetworkTest {

    @Autowired
    WebTestClient web;

    @Test
    void genuineHttpBasicWorksAcrossNetworkBoundary() {
        web.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "analyst", "lab-pass-123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("analyst");
    }

    @Test
    void wrongPasswordReturns401OnRealHttpServer() {
        web.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "analyst", "bad-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingBasicHeaderReturns401OnRealHttpServer() {
        web.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validButUnauthorizedRoleReturns403OnNetwork() {
        web.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth(
                "analyst", "lab-pass-123"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Four network tests** confirm that HTTP Basic headers actually travel through Netty + Spring WebFlux. This is still loopback HTTP in tests; it does not prove TLS certificates, reverse proxies, WAFs, ingress, sticky sessions, or multi-node deployments.

`RANDOM_PORT` avoids port collisions across CI jobs. `@AutoConfigureWebTestClient` automatically binds the base URL to the running server on its random port; never hardcode `localhost:8080` in integration tests.

**Total example suite:** 22 filter tests + 4 network tests = **26 JUnit test methods**. Those counts and PASS results are expected when you run Maven in a workspace with dependencies, not an execution performed here.

## 15. Minimum coverage checklist before release

| Test ID | Input | Route | Key assertion | Test role |
| --- | --- | --- | --- | --- |
| AUTH-01 | Missing header | `/api/me` | 401 | Private requires Basic |
| AUTH-02 | analyst / valid password | `/api/me` | 200, right username | Basic + BCrypt |
| AUTH-03 | admin / valid password | `/api/me` | 200 | Multiple users |
| AUTH-04 | analyst / wrong password | `/api/me` | 401 | Must verify password |
| AUTH-05 | Unknown user | `/api/me` | 401 | No auto-provision user |
| AUTH-06 | Empty password | `/api/me` | 401 | No fallback credential |
| AUTH-07 | Malformed Base64 | `/api/me` | 401 | Parsing does not bypass auth |
| AUTH-08 | Basic without delimiter | `/api/me` | 401 | Non-standard header |
| AUTH-09 | Bearer scheme | `/api/me` | 401 | Does not accept unintended scheme |
| AUTH-10 | Colon in password | `/api/me` | 200 | Splits on first colon |
| AUTH-11 | No auth | `/public/ping` | 200 | Public not blocked |
| AUTHZ-01 | Valid analyst | `/api/reports` | 200 | ANALYST role |
| AUTHZ-02 | Valid admin | `/api/reports` | 200 | ADMIN role |
| AUTHZ-03 | Valid analyst | `/api/admin` | 403 | Authn != authz |
| AUTHZ-04 | Valid admin | `/api/admin` | 200 | ADMIN |
| AUTHZ-05 | No auth | `/api/admin` | 401 | Anonymous lacks ADMIN |
| CSRF-01 | analyst Basic, missing CSRF | POST reports | 403 | Basic can be cached by browser |
| CSRF-02 | analyst Basic + csrf() | POST reports | 201 | CSRF + sufficient role |
| CSRF-03 | Wrong password + csrf() | POST reports | 401 | CSRF does not replace password |
| STATE-01 | Next request omits header | `/api/me` | 401 | Basic identity not persisted |
| HTTP-01 | 401 challenge | `/api/me` | WWW-Authenticate Basic | Protocol contract |
| NET-01 | Real Basic over TCP | `/api/me` | 200 | Network integration |

You can use this table as a test plan for automation/QA, though it does not replace actual JUnit code. Some teams also add unauthorized POST body/Content-Type, disabled/locked users, password rotation, backend exceptions, and rate limits; those require configuring additional providers and policies and cannot be inferred from the default lab.

## 16. Testing HTTP Basic with curl

Start Spring Boot after setting **local** secrets. With Bash:

~~~bash
export LAB_ANALYST_PASSWORD="lab-pass-123"
export LAB_ADMIN_PASSWORD="admin-pass-456"
export LAB_COLON_PASSWORD="pa:ss"
mvn spring-boot:run
~~~

These values are **public demo passwords**; never use them in public environments. With PowerShell:

~~~powershell
$env:LAB_ANALYST_PASSWORD = "lab-pass-123"
$env:LAB_ADMIN_PASSWORD = "admin-pass-456"
$env:LAB_COLON_PASSWORD = "pa:ss"
mvn spring-boot:run
~~~

Without matching passwords, the app fails fast before opening service endpoints.

Call the public endpoint:

~~~bash
curl -i "http://localhost:8080/public/ping"
~~~

Expected body:

~~~json
{"status":"up"}
~~~

Call the private endpoint without a Basic header:

~~~bash
curl -i "http://localhost:8080/api/me"
~~~

Expected status: `HTTP/1.1 401` and a Basic challenge header per entry point. Use curl with a password prompt so the plaintext password does not appear in command-line arguments:

~~~bash
curl -i --user analyst "http://localhost:8080/api/me"
~~~

Enter `lab-pass-123` when prompted. Expected JSON:

~~~json
{"username":"analyst"}
~~~

For `GET /api/admin` with valid analyst Basic, expect 403. With valid admin Basic, expect 200 with:

~~~json
{"section":"admin"}
~~~

**Environment limits:** Plaintext localhost HTTP URLs are strictly for the lab. In production, use HTTPS, protect password entry, and never copy Basic headers into issues, logs, screenshots, or CI. Passing `--user username:password` directly to curl can expose the password in process lists and shell history; use interactive prompts or vault-aware tooling.

## 17. Special case: Basic credentials in browsers and CSRF

A common misconception: "HTTP Basic is header-based and uses no session, so CSRF can be disabled completely." This is **not true in every scenario**.

Once a user authenticates with Basic, browsers can cache and automatically resend `Authorization: Basic ...` to the same protected origin. An attacker can trick the browser into issuing cross-site state-changing requests, making Basic **an ambient credential as well**. Whenever an application is accessed by browsers and exposes `POST`, `PUT`, `PATCH`, or `DELETE`, CSRF must be evaluated.

In the lab, CSRF stays enabled and `POST /api/reports` is tested:

~~~java
// Valid password but missing CSRF token:
client.post().uri("/api/reports")
    .headers(h -> h.setBasicAuth(
        "analyst", "lab-pass-123"))
    .exchange().expectStatus().isForbidden();

// Valid password + valid mock CSRF token:
client.mutateWith(csrf())
    .post().uri("/api/reports")
    .headers(h -> h.setBasicAuth(
        "analyst", "lab-pass-123"))
    .exchange().expectStatus().isCreated();
~~~

`csrf()` in `spring-security-test` sets a **valid token for the security test context**; it does not mean a production client can forge a similar token. Real applications need proper browser token issuance/submission, SameSite cookies, Origin/Referer checks, or a BFF/session architecture depending on the scenario.

If an API truly serves only machine-to-machine clients with no browser/cookie/auto-sent credentials and no CSRF threat by design, you may **decide to disable CSRF on the appropriate chain** after a clear threat-model review. Never use "Basic" as the sole excuse, and never disable CSRF on chains with sessions/form login.

## 18. Why might a 401 test produce unexpected results?

If missing Basic returns a `302` redirect:
- `formLogin` may still be enabled, selecting a browser-oriented entry point.
- The test may be using Servlet `MockMvc`/MVC config instead of WebFlux.
- A custom authentication entry point altered the behavior.
- The private route does not match the security matcher you assumed.

If a wrong password returns `200`:
- `mockUser()`/`@WithMockUser` set an identity beforehand.
- A custom filter or `permitAll()` matcher is overly broad.
- The security test did not apply `springSecurity()` or bypassed security WebFilters.
- A custom `ReactiveAuthenticationManager` returned an authenticated Authentication without verifying the password.
- Another HTTP session/Basic cache left the request authenticated; check test client state.

If valid Basic returns `401`:
- Password hash does not match encoder, or account is disabled/locked.
- Username case sensitivity or character encoding mismatch between client and server.
- `MapReactiveUserDetailsService` lacks the test user, or test properties were not loaded.
- Multiple `SecurityWebFilterChain`s exist and the request hit a different chain.
- Security context was read incorrectly using Servlet ThreadLocal code; use Reactor Context/`AuthenticationPrincipal`.

If valid Basic returns `403`:
- Authentication succeeded, yet role/authority is missing.
- Basic user has `ROLE_ANALYST` while the route requires `ROLE_ADMIN`.
- CSRF token is missing for a state-changing request.
- Business authorization forbids the tenant/object, or `anyExchange().denyAll()` matched first.
- Route/method matcher mismatch (e.g., `POST` vs `GET`).

**Never fix tests by changing every assertion to `isOk` or disabling security.** Cross-check routes, headers, managers, stored BCrypt hashes, security chain ordering, and error responses.

## 19. Multi-valued headers, whitespace, and encoding edge cases

RFC 7617 Basic credentials require consistent syntax. Cases worth adding negative tests for:

- `Authorization: Basic` missing credentials.
- `Authorization: Basic !!!` containing invalid Base64.
- Valid Base64 whose decoded text contains no `:`.
- Empty or non-existent username; empty password.
- Different scheme prefix such as `Bearer` or a custom API key.
- Multiple `Authorization` header values; server/proxy header merging must not be ambiguous.
- Spaces, tabs, or newline/control characters inside credentials.
- Inconsistent Unicode/charset handling in usernames.
- Decoded string containing `:` inside the **password**, not the username.

**Do not assume every implementation returns 401 for duplicated Authorization headers**: connectors/proxies may fold them, or the server may pick one or reject them. More importantly, **no bypass must exist**; test against your real version, reverse proxy, and connector to define the exact contract. If policy mandates strictly one Authorization value, create a converter/filter rejecting duplicates before authentication and test over the network.

A custom decoder should cap header length so huge Base64 payloads cannot exhaust CPU/memory. Never log entire headers when debugging malformed requests.

### 19.1. Java code building a Basic header for negative tests

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(
    "analyst:wrong-password".getBytes(
        StandardCharsets.ISO_8859_1));
String header = "Basic " + encoded;
~~~

For positive tests, **prefer** `HttpHeaders.setBasicAuth(username,password)` because the framework handles encoding properly, keeping tests short and readable. Encode Base64 manually only when intentionally testing malformed/edge conditions.

## 20. Boundaries outside the lab scope

**Password policy:** The lab uses bcrypt hashes and hardcoded dummy test users. Production requires password rotation, account lock/disable, credential stuffing protection, MFA for human identities, breach checks, and auditing. For machine-to-machine APIs, consider OAuth2 Client Credentials, mTLS, or workload identity rather than long-lived Basic credentials.

**User enumeration:** Even with a generic 401 status, processing time for an unknown username vs a wrong password can differ due to DB lookups/BCrypt. Limiting timing leaks may require dummy BCrypt checks, rate limits, and proper telemetry; never claim HTTP requests are constant-time merely because error messages match.

**Database/outage:** If `ReactiveUserDetailsService` errors because the DB is unavailable, never turn the error into an authenticated user or grant anonymous access. Fail closed; status mapping depends on security exception handling. Alert dependency outages separately rather than reporting mass wrong-password errors.

**Rate limits and monitoring:** Detect repeated failed logins per IP/account/workload without logging raw `Authorization` headers. Add quotas, backoff, and CAPTCHA/MFA where appropriate for browser flows, while avoiding self-inflicted DoS via uncontrolled lockouts.

**Basic challenge UX:** Browsers may cache credentials and pop up a login dialog. This may differ from SPA/mobile expectations; 401 responses and `WWW-Authenticate` may need customization, while keeping Basic protocol semantics clear.

**Domain auth:** `ROLE_ANALYST` suffices to GET reports in the lab, which does not imply permission to read every tenant's reports. Services/DB queries must enforce owner/tenant/resource ownership on real data.

## 21. Organizing tests for reliable CI

A suitable CI layout:

~~~text
mvn clean test
  -> BasicFilterTest:
       Basic header parsing + BCrypt + 401/403/200 + CSRF
  -> BasicNetworkTest:
       Netty HTTP real server + valid/invalid credentials
  -> surefire-reports:
       Redacted XML/JUnit logs and summary
~~~

Recommendations:
- Run tests on a pinned Spring Boot version and JDK 17+.
- Never use live production passwords/accounts.
- Each test supplies its own credentials without carrying state from other tests.
- Do not depend on port 8080 for network tests; use a random port.
- Never disable security in a `test` profile just to speed up tests.
- Monitor flakiness from DB/network/clock; the lab has no external DB.
- When upgrading Spring Security, re-run negative cases and challenge header semantics.
- Avoid enabling HTTP header wiretaps in CI logs.
- Add dedicated TLS/proxy and disabled-user tests if production depends on them.

**Passing tests alone cannot guarantee perfect security.** Yet a failing negative test (e.g., wrong password returning 200) is a critical signal that must be fixed before deployment.

## 22. Common mistakes in HTTP Basic testing

1. Using `mockUser()` to claim username/password verification works.
2. Testing only 200 with valid credentials while forgetting invalid ones.
3. Hardcoding real passwords in source/test fixtures.
4. Using `@WebFluxTest` while forgetting to import the custom `SecurityWebFilterChain`.
5. Testing the controller standalone without `springSecurity()` and thinking auth passed.
6. Booting `MockMvc` in a WebFlux application.
7. Sending `Bearer` when the server only configures Basic.
8. Transmitting plaintext passwords over internet HTTP because "it's Base64".
9. Logging the `Authorization` header to debug 401s.
10. Confusing wrong-password 401 with missing-role 403.
11. Confusing CSRF 403 with wrong password.
12. Not testing the `WWW-Authenticate`/client challenge contract.
13. Accidentally enabling both formLogin and Basic, getting 302 instead of 401.
14. Not configuring `NoOpServerSecurityContextRepository` when per-request Basic semantics are desired.
15. Opening every route via `anyExchange().permitAll()`.
16. Using a single admin account across all tests so role bugs go unseen.
17. Crafting Base64 manually with the wrong charset/colon delimiter and blaming the server.
18. Checking only HTTP status without asserting JSON does not leak passwords.
19. Disabling CSRF unconditionally because "Basic has no cookies".
20. Not testing a subsequent headerless request, missing accidental session persistence.
21. Skipping Netty tests when relying on proxies/header forwarding.
22. Lacking rate limits or alerts for brute-force attempts in production.
23. Conflating unknown users and DB outages in operations.
24. Putting passwords into curl command lines, shell history, and screenshots.
25. Changing acceptance criteria to arbitrary expectations when a security test fails.

## 23. Practice exercises

**A — Authentication matrix:** Add 401 tests for unknown username, wrong password, empty password, malformed Base64, Basic without `:`, and Bearer scheme. Prove none return 200 on private routes.

**B — Authorization:** Log in as analyst using real Basic, call `/api/admin` and expect 403. Switch to admin with valid password and expect 200. Explain why these two outcomes differ from an authentication failure.

**C — Browser CSRF:** POST with valid Basic but missing CSRF → 403; add `csrf()` in WebTestClient → 201. Explain why production needs a real CSRF token issuance mechanism rather than relying on mocks.

**D — Colon delimiter:** Account `colon` has password `pa:ss`; verify the Basic header still parses properly by splitting on the **first** colon.

**E — WWW-Authenticate:** Verify the Basic challenge on unauthenticated requests; customize the realm and update the assertion without leaking account details.

**F — Network integration:** Run `BasicNetworkTest` on a random port, ensuring Basic headers reach Netty/WebFlux cleanly. Test behind a reverse proxy in staging.

**G — Mock pitfalls:** Write a `mockUser` test reading reports even though the DB password is wrong, then explain why this is not a bug in mocking but a mismatched test goal.

**H — No persistence:** Send a valid Basic request, then omit the header on the next request; verify 401 and inspect cookies/WebSession if the app changes config.

**I — Error sanitization:** Log 401/403 status and a safe correlation ID without logging Authorization/passwords/BCrypt hashes. Write a test or integration assertion for the logging filter.

**J — Production provider:** Replace `MapReactiveUserDetailsService` with R2DBC/LDAP/custom manager in staging, keeping credential tests and adding disabled/locked user cases.

**K — Brute force:** Trigger multiple login failures in a controlled environment, apply IP/account rate limiting, and verify account existence is not leaked via body/status.

**L — HTTPS:** Use a TLS test certificate in staging and verify no Basic credentials appear on unencrypted channels or proxy logs.

## 24. Checklist before calling the test suite complete

- [ ] Private endpoints reject anonymous requests.
- [ ] Valid username/password Basic returns 200 and the right principal.
- [ ] Invalid password/unknown username returns a generic 401.
- [ ] Malformed/missing headers and wrong schemes cannot bypass auth.
- [ ] `WWW-Authenticate` is verified per client contract.
- [ ] Account roles from `UserDetails` are enforced accurately on routes.
- [ ] Authenticated users lacking a role receive 403, distinct from 401.
- [ ] No `mockUser` is used in tests meant to prove BCrypt credential verification.
- [ ] `WebTestClient` binds ApplicationContext with `springSecurity()`.
- [ ] At least a few tests run over real Netty HTTP on a random port.
- [ ] Authentication is not persisted in sessions when per-request Basic is required.
- [ ] CSRF is evaluated for browser Basic and state-changing routes.
- [ ] No secrets/hashes appear in JSON responses, logs, exceptions, or screenshots.
- [ ] JDK/Maven/Spring Boot versions are explicit, without assuming tests were already executed.
- [ ] Distinct debugging steps exist for 401 authn, 403 authz, and 403 CSRF.
- [ ] TLS, secret management, and rate limits are planned for production.
- [ ] Tenant/owner data access is still enforced in services/DB, not just HTTP roles.

## 25. Self-check questions

1. Which header does HTTP Basic send, and does Base64 encrypt the password?
2. Why must Basic run over HTTPS?
3. How does `HttpHeaders.setBasicAuth` improve tests over building the header manually?
4. Why is `WebTestClient` `springSecurity()` needed when binding to ApplicationContext?
5. Does `mockUser` verify BCrypt passwords?
6. Should valid credentials lacking ADMIN return 401 or 403?
7. Why does a 403 from CSRF not mean the password is wrong?
8. Can browsers automatically resend cached Basic credentials?
9. Does `NoOpServerSecurityContextRepository` eliminate every `WebSession` created by CSRF?
10. Why can a password containing a colon still be valid in Basic?
11. Is a `Bearer` token accepted when security only enables Basic?
12. What result should be observed when a follow-up request omits the Authorization header?
13. How do you verify the Basic challenge without hardcoding the realm?
14. Should an API reveal different reasons when a user does not exist vs when a password is wrong?
15. When multiple `SecurityWebFilterChain`s exist, what must tests verify?
16. When using the `@WebFluxTest` slice, how do you avoid dropping the security config?
17. Why doesn't a valid Basic header grant access to another tenant's data?
18. If `BasicNetworkTest` passes on localhost, are TLS and proxies already proven?
19. Why include negative tests for header parsing rather than only 200 cases?
20. When the account store dependency is down, should the server treat authentication as successful?

## 26. References

- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `ServerHttpSecurity`, reactive user details, and `SecurityWebFilterChain`.
- [Spring Security — Testing Authentication (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`/`@WithMockUser` and test security context.
- [Spring Security — Testing with CSRF (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `SecurityMockServerConfigurers.csrf()`.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): route authorization rules.
- [Spring Security — WebFlux HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/passwords/http-basic.html): Basic authentication in WebFlux.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `WebTestClient`, random port, and test slices.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToApplicationContext`, server response assertions, and HTTP testing.
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): headers, Base64, challenge/realm, delimiter/charset.
- [RFC 7235 — HTTP Authentication](https://www.rfc-editor.org/rfc/rfc7235): `WWW-Authenticate` challenge semantics (obsoleted by RFC 9110).
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): 401/403 and HTTP authentication.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): password/credential errors and preventing enumeration.
- [OWASP — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF when browsers auto-send credentials.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): BCrypt and password hashing.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): HTTPS/TLS and credential confidentiality.

**Conclusion:** In Spring Security Reactive, **proper HTTP Basic testing** means sending real `Authorization: Basic ...` headers via `WebTestClient.headers(h -> h.setBasicAuth(...))` and observing responses from `SecurityWebFilterChain` + `ReactiveAuthenticationManager` + `PasswordEncoder`. Valid username/password on an authorized route → 200; missing/invalid credentials → 401; authenticated but lacking role → 403. Never use `mockUser()` to prove password verification, never treat Base64 as encryption, and never disable CSRF merely because Basic does not use sessions. Combine in-memory and Netty network tests with negative header, role, and CSRF cases to avoid false confidence.