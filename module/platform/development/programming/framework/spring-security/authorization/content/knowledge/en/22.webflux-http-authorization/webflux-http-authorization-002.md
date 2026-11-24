# `pathMatchers`, HTTP Methods, and Rule Ordering in Spring Security WebFlux

## Goal and a real-world authorization bug

A reporting service exposes these APIs:

| Request | Policy |
| --- | --- |
| `GET /api/status` | Public |
| `GET /api/reports/public/guide` | Public |
| `GET /api/reports/admin/audit` | `ROLE_ADMIN` only |
| `GET /api/reports/42` | Authority `report:read` |
| `POST /api/reports` | Authority `report:write` |
| `DELETE /api/reports/42` | Authority `report:delete` |
| All other methods/paths | Deny |

If configured as:

```java
// WRONG: the broad GET rule above shadows the admin rule below.
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")
    .anyExchange().denyAll()
)
```

then someone with only `report:read` can pass HTTP authorization on `GET /api/reports/admin/audit`: the `GET /api/reports/**` matcher matched first. **Spring Security evaluates rules in declaration order; it does not automatically pick the most specific path rule.**

Reordering them:

```java
.authorizeExchange(ex -> ex
    .pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")
    .pathMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("report:read")
    .anyExchange().denyAll()
)
```

is the right solution within a single chain.

This lesson belongs to the **HTTP on WebFlux** section of Spring Security authorization, focusing on:

1. Overloads of `pathMatchers`, HTTP method matching, and path wildcards.
2. The **first matching rule wins** principle in `authorizeExchange`.
3. Distinguishing `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, and `denyAll`.
4. The relationship between `SecurityWebFilterChain`, `securityMatcher`, `@Order`, and rules inside a chain.
5. Configuring a real WebFlux application with Spring Boot 3.5.8 / Java 17.
6. Integration tests with `WebTestClient`, `mockUser`, and CSRF for GET/POST/DELETE, public, and admin routes.
7. Security bugs arising from overly broad fallbacks, CORS, HEAD/OPTIONS, URL normalization, and missing object-level authorization.

Principle: **place sensitive/specific rules before broad rules, open only the exact method/path combinations needed, put a deny fallback at the end, and test overlapping cases.**

## 1. WebFlux differs from Servlet: do not confuse the two DSLs

| Spring MVC / Servlet | Spring WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| `requestMatchers(...)` | `pathMatchers(...)`, `matchers(...)` |
| `HttpServletRequest` | `ServerWebExchange` |
| `MockMvc` | `WebTestClient` |
| `AuthorizationManager` | `ReactiveAuthorizationManager` |

WebFlux uses reactive `WebFilter`s; do not simply rename `HttpSecurity` to `ServerHttpSecurity` while keeping Servlet DSL methods. The following examples use Spring WebFlux exclusively.

A request flows through:

```text
Client / HTTP request
         |
         v
WebFilterChainProxy
         |
         v
Select the first matching SecurityWebFilterChain
    based on securityMatcher and @Order
         |
         v
Authentication + CSRF/CORS + other WebFilters
         |
         v
authorizeExchange in the selected chain
         |
   Evaluate rules in declaration order
         |
         v
First matching rule -> ALLOW or DENY
         |
         +--> ALLOW: controller / WebFlux handler
         |
         +--> DENY: authentication entry point
                    or access-denied handler
```

**Two distinct orderings:**

- **Chain selection order:** `SecurityWebFilterChain` beans have `@Order`; `securityMatcher` determines whether a request belongs to the chain.
- **Rule selection order:** once a chain is selected, `authorizeExchange` evaluates that chain's matchers in the exact order you declared them.

Spring neither aggregates permissions across all chains nor applies every rule that matches.

## 2. Understanding the forms of `pathMatchers`

### 2.1. Path only, without restricting HTTP method

```java
.pathMatchers("/api/reports/**").authenticated()
```

This rule does not distinguish GET, POST, PUT, PATCH, DELETE, or HEAD. If it precedes a DELETE rule requiring `report:delete`, any logged-in user can pass HTTP authorization when calling DELETE, because the broad rule already allowed it.

Do not use a method-agnostic path matcher when each action requires its own permission level.

### 2.2. Both method and path

```java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.pathMatchers(HttpMethod.POST, "/api/reports")
    .hasAuthority("report:write")
.pathMatchers(HttpMethod.DELETE, "/api/reports/*")
    .hasAuthority("report:delete")
```

Each matcher must match both **the HTTP method and the path**.

| Request | Matches GET rule? | Matches POST rule? | Matches DELETE rule? |
| --- | --- | --- | --- |
| `GET /api/reports/42` | Yes | No | No |
| `POST /api/reports` | No | Yes | No |
| `DELETE /api/reports/42` | No | No | Yes |
| `PATCH /api/reports/42` | No | No | No |
| `GET /api/reports/admin/audit` | Yes if broad GET rule precedes admin rule | No | No |

Unmatched methods fall through to subsequent rules. If the fallback is `denyAll`, they are denied instead of inheriting GET permissions.

### 2.3. Method only

```java
.pathMatchers(HttpMethod.GET)
    .hasAuthority("report:read")
```

This can match **every GET in the chain**, including URLs unrelated to reports. Do not place such a rule ahead of public/admin exceptions unless you intentionally want that authority on all GETs.

### 2.4. Catch-all with `anyExchange`

```java
.anyExchange().denyAll()
```

This applies to requests not yet matched in the current chain. Place it last so it does not shadow subsequent rules.

You may use `.anyExchange().authenticated()` in applications that intentionally require only login for all new URLs, but for allowlist-based APIs, **`denyAll()` is safer when adding new endpoints**. Never use `.anyExchange().permitAll()` as a fallback for sensitive APIs.

### 2.5. `matchers` with `ServerWebExchangeMatcher`

```java
.matchers(customServerWebExchangeMatcher)
    .access(customReactiveAuthorizationManager)
```

This is a **configuration fragment**, not a standalone Java file. Use it when path + method cannot express the context. The matcher/manager must obtain user/tenant/resource data from trusted sources, never treating a client-supplied header as proof of authentication.

## 3. Path syntax: `*`, `**`, `{id}`

WebFlux's `pathMatchers` uses `PathPatternParserServerWebExchangeMatcher`, built on Spring's `PathPattern`.

| Pattern | Typical meaning |
| --- | --- |
| `/api/status` | A specific path |
| `/api/reports/*` | A single segment immediately after `/api/reports/` |
| `/api/reports/{id}` | A single segment bound to variable `id` |
| `/api/reports/**` | Paths under the reports branch, including deeper segments |
| `/api/reports/admin/**` | Paths under the admin branch |
| `/api/**` | Broad API branch |
| `/**` | Catch-all path |

The path `/api/reports/admin/audit` has multiple segments after `/api/reports`, so `/api/reports/**` can match it too. Spring Security does not automatically prioritize `/api/reports/admin/**` if you place it afterward.

**Do not assume `PathPattern` is a filesystem glob or follows every rule of `AntPathMatcher`.** `**` must appear in positions supported by the parser. Keep patterns simple and run integration tests against real paths.

### 3.1. Security matchers and controller routes are not the same thing

A controller might declare:

```java
@GetMapping("/api/reports/admin/audit")
public Mono<String> audit() {
    return Mono.just("AUDIT");
}
```

WebFlux selects the handler by route mapping, whereas `authorizeExchange` selects the rule by **security configuration order**. A narrow controller route does not cause a narrow security rule to be evaluated first.

### 3.2. Trailing slashes, letter casing, URL encoding

Cases such as `/api/status` vs `/api/status/`, uppercase/lowercase, percent-encoded paths, semicolons, double slashes, or reverse-proxy rewrites may be handled differently by parsers and gateways. Do not assume they are equivalent when designing security.

For critical APIs, test paths after passing through the proxy and verify which path/method Spring Security actually sees. Do not "fix" routing mismatches by opening a broad `permitAll("/api/**")`.

## 4. First matching rule: common misconfigurations

### Mistake A: Broad report rule before admin

```java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("report:read")
.pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
    .hasRole("ADMIN")
```

A user with only `report:read` gets standard read access applied to the admin URL. Swap the order so admin comes before reports.

### Mistake B: Broad public before private

```java
.pathMatchers("/api/**").permitAll()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
```

The second rule is shadowed. Clients can access API URLs under the public rule. `permitAll` should apply only to genuinely public URLs/methods.

### Mistake C: `authenticated()` before write permissions

```java
.pathMatchers("/api/reports/**").authenticated()
.pathMatchers(HttpMethod.DELETE, "/api/reports/*")
    .hasAuthority("report:delete")
```

A logged-in user without delete permission passes HTTP authorization on the first rule. `authenticated` is **not** `report:delete`.

### Mistake D: Method-only public GET at the top

```java
.pathMatchers(HttpMethod.GET).permitAll()
.pathMatchers(HttpMethod.GET, "/api/reports/admin/**")
    .hasRole("ADMIN")
```

Every GET in the chain is permitted publicly, including the admin branch.

### Mistake E: Overly permissive fallback

```java
.anyExchange().authenticated()
```

A new `/api/reports/export` controller or new HTTP method can be exposed to all logged-in users without review. For an allowlist policy, prefer:

```java
.anyExchange().denyAll()
```

### Mistake F: Catch-all declared before specific rules

```java
.anyExchange().denyAll()
.pathMatchers("/api/status").permitAll()
```

The catch-all must be last. Depending on the DSL version, declaring rules after a catch-all may fail configuration validation or fail to match your intent; never rely on accidental behavior.

## 5. `hasRole` versus `hasAuthority`

```java
.hasRole("ADMIN")
```

by default requires a `GrantedAuthority` of **`ROLE_ADMIN`**, not `"ADMIN"`.

```java
.hasAuthority("ROLE_ADMIN")
```

requires the exact string `ROLE_ADMIN` and is usually equivalent to `hasRole("ADMIN")` if the default prefix is kept.

```java
.hasAuthority("report:read")
```

requires the exact authority `report:read`, without automatically adding `ROLE_`.

| API | Authority required under default config |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ADMIN")` | `ADMIN` |
| `hasAuthority("report:read")` | `report:read` |

If an application customizes the role prefix or maps JWT scopes/roles specially, check the actual authorities on the `Authentication`. Never rely on role display names from the frontend.

## 6. Choosing rules by HTTP method: GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS

A resource might have:

```text
GET    /api/reports/42 -> report:read
DELETE /api/reports/42 -> report:delete
PUT    /api/reports/42 -> not supported yet, deny
```

**DELETE does not inherit GET permissions.** Use method matchers to bind each action.

### 6.1. HEAD

HEAD can reveal metadata such as ETag, content length, or object existence. Do not assume a GET rule automatically covers HEAD at the security layer. If the API supports HEAD, configure and test it explicitly:

```java
// ADDITIONAL SNIPPET, must be placed in the right order relative to public/admin.
.pathMatchers(HttpMethod.HEAD, "/api/reports/**")
    .hasAuthority("report:read")
```

Routes/handlers may support HEAD under WebFlux's own rules, but **security matchers still need to check methods according to the contract**.

### 6.2. OPTIONS and CORS

A browser may send a preflight:

```http
OPTIONS /api/reports
Origin: https://client.example
Access-Control-Request-Method: POST
```

If CORS is misconfigured, the browser may block the real request even when the user is authorized. However, **CORS is not an authentication/authorization mechanism** and does not protect against non-browser clients.

Configure CORS for only the origins, methods, headers, and credentials truly needed, handling preflight through the appropriate WebFlux/Spring Security mechanism. Never "fix" it with a blanket `permitAll` or wildcard origins combined with credentials.

### 6.3. CSRF and POST/DELETE

Spring Security WebFlux enables CSRF protection by default. Cookie/session-based POST, PUT, PATCH, and DELETE requests typically require a token. Consequently, a caller with `report:write` can still receive **403 due to a missing CSRF token**, not because `hasAuthority` failed.

In integration tests, use:

```java
client.mutateWith(mockUser("writer")
        .authorities(new SimpleGrantedAuthority("report:write")))
    .mutateWith(csrf())
    .post()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

This is a **test snippet**, assuming `client` already has `springSecurity()` applied; the full example follows below.

Do not disable CSRF just because a POST test failed. For stateless bearer-token APIs that do not use cookies, the threat model differs, but the decision must be based on the real authentication mechanism and clients.

## 7. Complete demo: Spring Boot 3.5.8 + Java 17 + WebFlux

The following project focuses on verifying **HTTP authorization rules**; handlers return demo strings and do not touch a database. Therefore, this example demonstrates route/security matchers and **does not by itself prove object-level authorization on reportId, owner, or tenant**.

### 7.1. Structure

```text
reactive-path-matcher-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PathMatcherApplication.java
    │   ├── WebSecurityConfig.java
    │   └── ReportController.java
    └── test/java/demo/
        └── PathMatcherSecurityTest.java
```

### 7.2. `settings.gradle`

```groovy
rootProject.name = 'reactive-path-matcher-demo'
```

### 7.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Declare only the WebFlux starter; do not mix `spring-boot-starter-web` (Servlet) into the example.

### 7.4. Spring Boot application

**`src/main/java/demo/PathMatcherApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathMatcherApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathMatcherApplication.class, args);
    }
}
```

### 7.5. Security config: specific rules first, broad rules after

**`src/main/java/demo/WebSecurityConfig.java`:**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/status")
                    .permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/public/**")
                    .permitAll()
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/admin/**")
                    .hasRole("ADMIN")
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("report:write")
                .pathMatchers(
                    HttpMethod.DELETE, "/api/reports/*")
                    .hasAuthority("report:delete")
                .pathMatchers("/api/**")
                    .denyAll()
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {

        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader-pass")
            .authorities("report:read")
            .build();

        UserDetails writer = User.withUsername("writer")
            .password("{noop}writer-pass")
            .authorities("report:write")
            .build();

        UserDetails deleter = User.withUsername("deleter")
            .password("{noop}deleter-pass")
            .authorities("report:delete")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            reader, writer, deleter, admin);
    }
}
```

**Explanation:**

1. GET status and GET public are method-specific public exceptions.
2. GET admin comes **before** the broad GET reports rule, blocking regular readers from admin.
3. GET reports requires `report:read`, POST reports requires `report:write`, and DELETE on a single report requires `report:delete`.
4. `/api/**` and all other URLs are denied if not explicitly allowed.
5. `httpBasic` provides authentication for the demo; seeded users only have the authorities specified and do not inherit extra permissions.
6. There is no `.csrf(...disable...)`; default CSRF still applies.
7. `"{noop}"` and demo passwords are **for learning only**, never for production. Production must use secure password hashing or OIDC/OAuth2/JWT with an appropriate identity provider.

### 7.6. Reactive controller

**`src/main/java/demo/ReportController.java`:**

```java
package demo;

import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/status")
    public Mono<String> status() {
        return Mono.just("OK");
    }

    @GetMapping("/api/reports/public/{name}")
    public Mono<String> publicReport(
            @PathVariable String name) {
        return Mono.just("PUBLIC:" + name);
    }

    @GetMapping("/api/reports/admin/audit")
    public Mono<String> audit() {
        return Mono.just("AUDIT");
    }

    @GetMapping("/api/reports/{id}")
    public Mono<String> report(
            @PathVariable Long id) {
        return Mono.just("REPORT:" + id);
    }

    @PostMapping("/api/reports")
    public Mono<String> create() {
        return Mono.just("CREATED");
    }

    @DeleteMapping("/api/reports/{id}")
    public Mono<String> delete(
            @PathVariable Long id) {
        return Mono.just("DELETED:" + id);
    }
}
```

The controller returns `Mono<String>` and performs no blocking I/O. `GET /api/reports/admin/audit` has a dedicated handler, yet authorization still depends on **matcher order in config**; controller mappings never fix security rules on their own.

## 8. Integration tests with `WebTestClient`

Spring Security provides WebFlux test support via `springSecurity()`, `mockUser()`, and `csrf()`.

**`src/test/java/demo/PathMatcherSecurityTest.java`:**

```java
package demo;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
class PathMatcherSecurityTest {

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

    private WebTestClient reader() {
        return client.mutateWith(
            mockUser("reader").authorities(
                new SimpleGrantedAuthority("report:read"))
        );
    }

    private WebTestClient writer() {
        return client.mutateWith(
            mockUser("writer").authorities(
                new SimpleGrantedAuthority("report:write"))
        );
    }

    private WebTestClient deleter() {
        return client.mutateWith(
            mockUser("deleter").authorities(
                new SimpleGrantedAuthority("report:delete"))
        );
    }

    private WebTestClient admin() {
        return client.mutateWith(
            mockUser("admin").roles("ADMIN")
        );
    }

    @Test
    void publicGetIsAvailableToAnonymous() {
        client.get().uri("/api/status").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");

        client.get().uri("/api/reports/public/guide").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("PUBLIC:guide");
    }

    @Test
    void reportReadUsesReadAuthority() {
        reader().get().uri("/api/reports/42").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("REPORT:42");

        writer().get().uri("/api/reports/42").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRuleWinsBeforeBroadGetReports() {
        // Has report:read but lacks ROLE_ADMIN.
        reader().get().uri("/api/reports/admin/audit").exchange()
            .expectStatus().isForbidden();

        // Admin only has ROLE_ADMIN, not report:read.
        admin().get().uri("/api/reports/admin/audit").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("AUDIT");
    }

    @Test
    void postAndDeleteHaveIndependentAuthorities() {
        writer().mutateWith(csrf())
            .post().uri("/api/reports").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("CREATED");

        reader().mutateWith(csrf())
            .post().uri("/api/reports").exchange()
            .expectStatus().isForbidden();

        deleter().mutateWith(csrf())
            .delete().uri("/api/reports/42").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("DELETED:42");

        reader().mutateWith(csrf())
            .delete().uri("/api/reports/42").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void csrfRemainsEnabled() {
        writer().post().uri("/api/reports").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownMethodAndPathsFailClosed() {
        reader().mutateWith(csrf())
            .put().uri("/api/reports/42").exchange()
            .expectStatus().isForbidden();

        reader().get().uri("/api/unlisted").exchange()
            .expectStatus().isForbidden();

        reader().get().uri("/outside-api").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousCannotReadProtectedReport() {
        client.get().uri("/api/reports/42").exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Why are these tests more trustworthy than testing only the controller?**

- `@SpringBootTest` loads the real security configuration and handlers.
- `bindToApplicationContext(...).apply(springSecurity())` wires the reactive security WebFilter into `WebTestClient`.
- `mockUser` grants only the specified authorities; it does not grant `report:read` to `writer`.
- The admin-without-read test **proves the admin rule is evaluated before the broad GET reports rule**.
- The reader-on-admin test **catches ordering regressions**, rather than only checking that admin succeeds.
- `csrf()` separates missing-CSRF errors from missing-authority errors in POST/DELETE tests.
- Deny tests use an authenticated user to verify HTTP 403 per the rules; anonymous protected GET verifies the 401 entry point.

These are integration tests for **HTTP authorization**, not a substitute for service/DB ownership tests. The demo handlers only return text and do not write or delete real data.

### 8.1. Running the application and tests

In the directory containing `build.gradle`, if you have the Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

If there is no wrapper yet, use a compatible Gradle installation to generate the wrapper or run `gradle test`/`gradle bootRun` once installed.

After the server starts, try:

```bash
curl -i http://localhost:8080/api/status
curl -i http://localhost:8080/api/reports/public/guide
curl -i -u reader:reader-pass http://localhost:8080/api/reports/42
curl -i -u admin:admin-pass http://localhost:8080/api/reports/admin/audit
```

This is an HTTP Basic demo; **never** use `{noop}`/plain passwords in production. For POST/DELETE, a `curl -u` with only Basic credentials may get 403 due to a missing CSRF token: use the `WebTestClient` tests above or integrate your frontend's actual CSRF mechanism.

### 8.2. Expected result matrix

| User | Request | Expected HTTP |
| --- | --- | ---: |
| Anonymous | `GET /api/status` | `200` |
| Anonymous | `GET /api/reports/public/guide` | `200` |
| Reader | `GET /api/reports/42` | `200` |
| Writer | `GET /api/reports/42` | `403` |
| Reader | `GET /api/reports/admin/audit` | `403` |
| Admin | `GET /api/reports/admin/audit` | `200` |
| Writer + CSRF | `POST /api/reports` | `200` |
| Reader + CSRF | `POST /api/reports` | `403` |
| Deleter + CSRF | `DELETE /api/reports/42` | `200` |
| Reader + CSRF | `DELETE /api/reports/42` | `403` |
| Writer, missing CSRF | `POST /api/reports` | `403` |
| Reader + CSRF | `PUT /api/reports/42` | `403` |
| Reader | `GET /api/unlisted` | `403` |
| Reader | `GET /outside-api` | `403` |
| Anonymous | `GET /api/reports/42` | `401` per HTTP Basic demo |

These statuses are **expected outcomes from the source code**, not a claim that the tests were executed in this environment. With other authentication entry points (Bearer, form login, session), 401/403/redirects may differ; ALLOW/DENY policies must be verified against the product contract.

## 9. Multiple `SecurityWebFilterChain`s: `@Order` and `securityMatcher`

An application can have a dedicated API chain and a fallback chain. **Do not include the following configuration alongside the `securityWebFilterChain` bean from section 7**: this is an alternative design to explain chain selection.

```java
// CONCEPTUAL CONFIG SNIPPET: imports and userDetailsService
// must be added if extracted into a standalone project.
@Configuration
@EnableWebFluxSecurity
class MultipleChains {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"))
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/status")
                    .permitAll()
                .pathMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

- For `GET /api/status`, the `@Order(1)` chain matches `/api/**`, and the status rule allows public access.
- For `GET /api/admin/audit`, it also enters the API chain, where the admin rule requires `ROLE_ADMIN`.
- For `GET /outside-api`, the API chain does not match, so the fallback chain denies it.
- `anyExchange()` inside the API chain does **not** mean every request across the entire system: the chain is only selected if `securityMatcher("/api/**")` matches.

**Trap:** if a catch-all chain has `@Order(1)` and the `/api/**` chain has `@Order(2)`, the catch-all may be selected first for every request. The strict rules in the API chain will never run. Order narrow-matcher chains first and broad fallbacks last.

Also check **coverage**: if no chain matches a URL, that request may bypass Spring Security WebFilters unexpectedly. An explicit fallback chain prevents gaps when new URLs are added.

The multi-chain config above intentionally omits report endpoints because it only illustrates chain ordering. In a real product, add the actual report rules into the API chain per your policy while still ending with `denyAll`.

## 10. Path variables, `ReactiveAuthorizationManager`, and data-level permissions

URL matchers do not verify ownership automatically. For example:

```java
.pathMatchers(HttpMethod.GET, "/api/reports/{id}")
    .hasAuthority("report:read")
```

This rule requires `report:read`, but it does **not** verify that report `{id}` belongs to the caller's tenant or that the caller has a READ ACE on it. For real data APIs, add policies in the service/repository layer or a custom `ReactiveAuthorizationManager<AuthorizationContext>`.

Example **config snippet** comparing a username in the path with the authenticated identity:

```java
.pathMatchers(
    HttpMethod.GET, "/api/users/{name}/profile"
)
.access((authentication, context) ->
    authentication
        .map(auth -> new AuthorizationDecision(
            auth.getName().equals(
                context.getVariables().get("name"))
        ))
        .defaultIfEmpty(new AuthorizationDecision(false))
)
```

`AuthorizationContext.getVariables()` provides URI template variables. This snippet only illustrates binding a path name; production code must handle anonymous callers and stable user identities, never relying on usernames that are only unique per tenant or self-declared by the client.

When permissions depend on a database, avoid blocking JDBC calls inside the reactive WebFilter event loop. Prefer non-blocking reactive data access/policy services or controlled adaptation. For sensitive updates, re-verify permissions and state inside the transaction or conditional SQL near the point of mutation to prevent **TOCTOU**.

`@EnableWebFluxSecurity` only enables web security; if you want `@PreAuthorize` on a **reactive service**, look into `@EnableReactiveMethodSecurity` and reactive return-type contracts. Never treat HTTP path authorization as a replacement for object permissions.

## 11. CORS, CSRF, proxy rewrites, and regression testing

An API deployed behind a gateway may receive `/api/reports/42` even when the external URL is `/service/api/reports/42`; matchers inspect the request/path that the Spring WebFlux backend actually sees. Test through the proxy in integration environments to avoid wrong assumptions about base paths, encoded slashes, double slashes, semicolons, and trailing slashes.

CORS controls browser cross-origin behavior; it does not grant `report:read` authority. CSRF protects state-changing requests under a cookie/session threat model. Both interact with web security, but **neither replaces** role or object authorization.

Minimum checklist whenever routes, rules, or framework versions change:

1. Test anonymous and authenticated callers for **every public exception**.
2. Test that a user with only `report:read` **cannot** access admin paths.
3. Test that an admin without read authority can still reach admin paths as required by business rules.
4. Test that GET/POST/DELETE on the same URL branch enforce **distinct permissions**.
5. Test that PUT/PATCH/HEAD/OPTIONS are not accidentally left open; add explicit CORS/HEAD rules when needed.
6. Test that new routes do not slip through an `authenticated` or `permitAll` fallback.
7. With multiple chains, test `@Order`, `securityMatcher`, and fallback coverage for remaining URLs.
8. Test CSRF with a valid token to verify authorization independently, and without a token to verify exploit protection.
9. Test paths after reverse-proxy rewrites and supported URL variants.
10. Test object/tenant/ACL permissions at the service layer, not just HTTP status codes.

### Common mistakes

| Problem | Cause | Fix |
| --- | --- | --- |
| Reader opens admin URL | Broad GET rule placed before admin | Put admin rule before reports rule |
| DELETE uses READ permission | `pathMatchers("/api/reports/**").authenticated()` placed first | Use method-specific authority rules |
| Every GET becomes public | `.pathMatchers(HttpMethod.GET).permitAll()` | Permit only specific path/method pairs |
| New endpoint opens automatically | `.anyExchange().authenticated()` or `.permitAll()` | Default deny, explicit allowlist |
| Admin gets 403 despite having `ADMIN` | `hasRole` looks for `ROLE_ADMIN` by default | Map authorities properly |
| POST gets 403 despite write authority | Missing CSRF token | Test with token, review CSRF policy |
| API chain is never selected | Catch-all chain has higher `@Order` | Narrow first, broad last |
| Routes outside chain are unprotected | Missing fallback `SecurityWebFilterChain` | Add deny fallback chain |
| Controller test passes while security fails | Test does not attach WebFilter chain | Use `.apply(springSecurity())` |
| Reader views another tenant's documents | HTTP rule ignores object ID | Use tenant-scoped service/repository |
| Slow policy DB lookups | Blocking I/O in reactive filter | Use reactive access with bounded timeouts |
| Behavior differs behind gateway | Path normalization/rewriting | Integration test with real URLs |

## 12. Self-assessment questions

**1.** Do these two rules combine?

```java
.pathMatchers("/api/**").authenticated()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
```

**Answer:** No. `/api/**` matches first; the subsequent admin rule is shadowed. Move the admin rule first.

**2.** Does `pathMatchers(HttpMethod.GET, "/api/reports/**")` match `DELETE /api/reports/42`?

**Answer:** No. The method must be GET.

**3.** Is `.pathMatchers("/api/reports/**").hasAuthority("report:read")` enough to protect DELETE?

**Answer:** No if the business requires `report:delete`; a path-only matcher does not distinguish HTTP methods.

**4.** When a user has `ROLE_ADMIN`, does `.hasRole("ADMIN")` match?

**Answer:** Yes with the default role prefix; `.hasAuthority("ADMIN")` is different.

**5.** Why must `GET /api/reports/admin/audit` be tested with a reader lacking the admin role?

**Answer:** To catch the bug where a broad GET reports rule shadows the admin rule.

**6.** Where should `anyExchange().denyAll()` be placed?

**Answer:** At the end of the chain's rule list, after all allowlist rules.

**7.** With two `SecurityWebFilterChain`s, which rules run first?

**Answer:** A chain is selected first by `@Order` and `securityMatcher`, and only then are the rules inside that selected chain evaluated.

**8.** If a POST request with valid authority but no CSRF token gets 403, does that mean the matcher is wrong?

**Answer:** No; CSRF may be blocking it. Test with `csrf()` to verify the authority rule independently.

**9.** Is `GET /api/reports/42` with `report:read` authority enough for data security?

**Answer:** Not yet. You also need to verify report ID, tenant, owner/ACL, and actual resource policies.

**10.** When a user belongs to multiple tenants, can we take the tenant directly from a query parameter and pass it into the policy?

**Answer:** No. The tenant must be verified via membership/identity server and the authoritative resource record.

## 13. Official documentation

- [Spring Security 6.5 – Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, and rule ordering.
- [Spring Security 6.5 – WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): `SecurityWebFilterChain`, `@EnableWebFluxSecurity`, multiple chains, and `@Order`.
- [Spring Security API – AbstractServerWebExchangeMatcherRegistry](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/AbstractServerWebExchangeMatcherRegistry.html): `pathMatchers` overloads and `anyExchange`.
- [Spring Security API – ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): reactive `ServerHttpSecurity` DSL.
- [Spring Security 6.5 – WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `.apply(springSecurity())` for WebFlux tests.
- [Spring Security 6.5 – Testing WebFlux Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, `@WithMockUser`.
- [Spring Security 6.5 – Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `mutateWith(csrf())`.
- [Spring Security 6.5 – CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html): protecting POST/PUT/DELETE per threat model.
- [Spring Framework – WebFlux Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): distinguishing route mapping from security matching.

**Conclusion:** WebFlux `pathMatchers` checks the path and optionally the HTTP method; matchers are evaluated **in declaration order**, and the first matching rule wins. Place specific branches before broad ones, separate READ/WRITE/DELETE permissions, keep `anyExchange().denyAll()` last, verify the `@Order` of multiple `SecurityWebFilterChain`s, and always test overlapping reader/admin cases with `WebTestClient`. HTTP-level authorization does not replace object/tenant permissions; data operations still need policies in services and the database.