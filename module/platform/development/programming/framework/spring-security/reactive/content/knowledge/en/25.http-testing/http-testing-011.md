# Verifying Multiple SecurityWebFilterChains and the Fallback Chain

*Spring Security - reactive · HTTP Testing Group · Java 17+ · Spring Boot 3.5.16 / Spring Security 6.x.*

## 1. Goal and Problem

A Spring WebFlux application may expose admin APIs, user APIs, public endpoints, and multiple authentication mechanisms. Instead of a single `SecurityWebFilterChain`, the application can declare multiple chains with `securityMatcher` and `@Order` priority.

**Decision mechanism:** Spring Security evaluates `SecurityWebFilterChain`s in priority order, **selects the first chain whose matcher matches**, and then applies authentication and authorization inside that chain. If the selected chain returns 401 or 403, Spring Security **does not** try subsequent chains looking for a more permissive rule.

A testing task more important than checking bean names is proving **which chain a request was routed into**, while also proving endpoints are allowed or blocked accurately.

After this lesson, you will be able to:

1. Understand `SecurityWebFilterChain`, `WebFilterChainProxy`, `ServerWebExchangeMatcher`, `@Order`, `securityMatcher`, and `authorizeExchange`.
2. Distinguish `securityMatcher` (selecting the entire chain) from `pathMatchers` (selecting rules **after** a chain is chosen).
3. Configure three overlapping chains: high-priority admin `/api/admin/**`, lower-priority API `/api/**`, and a fallback with no dedicated matcher.
4. Use `anyExchange().denyAll()` for a fail-closed fallback.
5. Test chain selection using a lab-only response header so 403 from authorization is never confused with 404 from a missing handler.
6. Write a Java 17+ Spring Boot WebFlux project and `WebTestClient` integration tests with real Basic authentication.
7. Test 200/401/403 statuses, path overlaps, similar prefixes, HEAD/POST, forged `X-User`/`X-Role` headers, and fallback coverage over real handlers.
8. Distinguish role/authorization denials from CSRF, CORS, redirects, and framework short-circuits.
9. Recognize the risks of omitting a catch-all chain or using a `permitAll` fallback.
10. Apply this testing approach when replacing Basic with OAuth2 Resource Server JWT, form login, or client certificates.

**Rule:** each request enters **the first matching chain**, with no "falling through" to the fallback after being denied. The fallback must be treated as part of the security policy, not a quick-fix workaround.

## 2. Multi-chain architecture

```text
GET /api/admin/report + HTTP Basic alice
                     |
                     v
          Spring Security WebFilterChainProxy
                     |
               @Order(1)
          matcher /api/admin/** ?
                     |
                    YES
                     |
                     v
             adminChain
          anyExchange.hasRole("ADMIN")
                     |
          alice only has ROLE_USER
                     |
                     v
                403 Forbidden
                     |
        DOES NOT check apiChain/fallbackChain
```

Another request:

```text
GET /public/ping
        |
        v
@Order(1) adminChain:   /api/admin/** -> NO
        |
        v
@Order(2) apiChain:     /api/**       -> NO
        |
        v
@Order(3) fallbackChain: match all   -> YES
        |
        v
GET /public/ping permitAll -> HTTP 200
```

`@Order(1)` has higher priority than `@Order(2)`. `/api/admin/report` matches both `/api/admin/**` and `/api/**`, so **`adminChain` must precede `apiChain`**.

### 2.1. `securityMatcher` is the chain selection condition

Example:

```java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
```

This is a `ServerWebExchangeMatcher` for the **entire chain**. If it does not match, Spring Security moves on to evaluate the next-priority chain.

### 2.2. `pathMatchers` is the authorization condition inside the chain

Example:

```java
http.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
        .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
        .anyExchange().denyAll());
```

These rules are evaluated **only inside the selected chain**. `anyExchange` here means remaining requests **within this chain**, not the entire application. If `adminChain` returns 403, the request does not continue into `apiChain` to ask for different permissions.

### 2.3. `@Order` differs from `SecurityWebFiltersOrder`

- `@Order` on a `@Bean SecurityWebFilterChain` determines **which chain is evaluated first**.
- `SecurityWebFiltersOrder` used in `ServerHttpSecurity.addFilterAt/Before/After` determines **a WebFilter's position inside a chain**.
- One cannot be swapped for the other.

### 2.4. The fallback chain

The fallback does not call `.securityMatcher(...)`; `ServerHttpSecurity`'s default matcher matches every request. Place it **last**.

```java
@Bean
@Order(3)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers(HttpMethod.GET,
                            "/public/ping").permitAll()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

The snippet above lacks full imports/config; the complete runnable file is in section 7. This fallback opens only `GET /public/ping`, **not** allowing authenticated users to hit uninventoried endpoints.

If **no chain matches** a request, Spring Security's `WebFilterChain` does not protect that request (aside from protections outside the chain). Hence a missing fallback or overly narrow matcher can expose handlers. A 404 from a missing handler **is not proof** that an endpoint has authorization.

## 3. Illustrative design: admin, api, and fallback

### 3.1. `adminChain`, `@Order(1)`

- Matcher `/api/admin/**`.
- HTTP Basic verifying Alice/Admin against the BCrypt user store.
- Every request entering the chain requires `hasRole("ADMIN")`.
- Observation header `X-Lab-Security-Chain: admin`.
- `GET /api/admin/report` has a real handler.
- `GET /api/admin/public` also has a real handler; **its name contains `public` yet it is not automatically public**.

### 3.2. `apiChain`, `@Order(2)`

- Matcher `/api/**`, which also encompasses `/api/admin/**` but has lower priority than admin.
- `GET /api/public`: `permitAll`.
- `GET /api/me`: `authenticated`.
- `anyExchange().denyAll()`: all other methods/routes.
- Observation header `X-Lab-Security-Chain: api`.
- `GET /api/hidden` has a real handler but is blocked by `denyAll`.
- `GET /api/adminX/data` has a real handler; segment `adminX` **does not** match `/api/admin/**`, so it enters the API chain and hits `denyAll`.

### 3.3. `fallbackChain`, `@Order(3)`

- Declares no `securityMatcher`; matches every request not claimed by the two chains above.
- `GET /public/ping`: `permitAll`.
- `anyExchange().denyAll()`: other routes are denied even for admin.
- Observation header `X-Lab-Security-Chain: fallback`.
- `GET /hidden` has a real handler but is blocked by `denyAll`.

### 3.4. Verification matrix

| Method / path | Chain | Principal | Expected |
| --- | --- | --- | --- |
| GET `/public/ping` | fallback | anonymous | 200 |
| GET `/api/public` | api | anonymous | 200 |
| GET `/api/me` | api | anonymous | 401 |
| GET `/api/me` | api | alice | 200, principal alice |
| GET `/api/me` | api | wrong Basic password | 401 |
| GET `/api/admin/report` | admin | anonymous | 401 |
| GET `/api/admin/report` | admin | alice | 403 |
| GET `/api/admin/report` | admin | admin | 200 |
| GET `/api/admin/public` | admin | anonymous | 401 |
| GET `/api/hidden` | api | alice | 403 |
| GET `/api/adminX/data` | api | alice | 403 |
| GET `/hidden` | fallback | alice | 403 |
| GET `/hidden` | fallback | admin | 403 |
| GET `/missing` | fallback | admin | 403 |
| GET `/hidden` | fallback | anonymous | 401 |
| HEAD `/api/public` | api | alice | 403 |
| POST `/api/public` | api | alice | 403 |
| GET `/api/admin/report` + X-Role ADMIN | admin | alice | 403 |

Status alone is only part of the picture. Tests must also assert the matching **chain marker**; otherwise a 403 could come from an entirely different chain, or from CSRF/handler/edge filters.

## 4. Why do tests need a chain identification marker?

A test observing `/api/admin/report` returning 403 does not prove `adminChain` was selected. It could be:
- A broad API chain matched the request and called `denyAll`.
- The fallback chain was applied.
- The request was rejected early by CSRF/CORS/another filter.
- No controller existed, returning 404 (or mismatch).

We place a lab-only `WebFilter` **inside each chain** and set response header `X-Lab-Security-Chain` via `response.beforeCommit`. Its value is `admin`, `api`, or `fallback`. The filter **does not** authenticate, authorize, read raw credentials, or modify `SecurityContext`.

The marker is placed at `SecurityWebFiltersOrder.FIRST` inside the chain. When a valid GET request enters the chain and is later blocked by Basic or `authorizeExchange`, the `beforeCommit` callback still gets to attach the marker. If a request is rejected by the HTTP parser, gateway, or firewall **before the chain**, the marker may be absent; that requires separate investigation rather than guessing chain selection.

**Use the marker only in demos/tests.** Production must not leak chain names, role policies, token payloads, or internal security infrastructure in response headers.

## 5. Ordering and scoping pitfalls

### 5.1. Placing a broad chain before a narrow chain

Antipattern:

```java
// WRONG ORDERING: /api/** can shadow /api/admin/**.
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher(
                            "/api/**"))
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .build();
}
```

If the API chain only requires `authenticated` and is evaluated first, Alice can reach the admin controller without `ROLE_ADMIN`. **There is no fallback to `adminChain` to "fix" permissions.** An overlap test checking the `admin` marker and Alice -> 403 acts as a guardrail against this bug.

### 5.2. Forgetting the fallback

Antipattern:

```java
@Bean
SecurityWebFilterChain onlyApi(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher(
                            "/api/**"))
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .build();
}
```

If only this chain exists, requests to `/hidden` are not protected by any Spring Security web chain. If `/hidden` has a controller returning data, it risks returning 200. Never assume Spring Boot creates an extra catch-all chain once custom chain beans exist.

Proper way to test: ensure a **real** `/hidden` handler exists, send valid Basic credentials, and expect **403 with the `fallback` marker**. Do not test only a URL lacking a controller and accept 404.

### 5.3. Fallback `authenticated` vs `denyAll`

- `.anyExchange().authenticated()` on the fallback lets **any logged-in user** call unlisted endpoints.
- `.anyExchange().permitAll()` makes the entire fallback public.
- `.anyExchange().denyAll()` blocks by default; specific public URLs use earlier `pathMatchers(...).permitAll()` rules.
- Never switch to `permitAll` just to make a failing 401/403 test "pass".

### 5.4. Method-specific allowlists

```java
.pathMatchers(HttpMethod.GET, "/api/public").permitAll()
```

does not automatically open `HEAD` or `POST`. Framework controllers can handle `HEAD` for a `@GetMapping`, yet **authorization matchers still distinguish HTTP methods**. For `POST`, the CSRF filter can also block before `denyAll`, so status 403 alone does not reveal which rule rejected the call.

### 5.5. Prefixes and normalized paths

`/api/admin/report` belongs to `admin`. `/api/adminX/data` belongs to `api`, not `admin`. `/api`, `/api/`, trailing slashes, encoded slashes/dots, case sensitivity, and forwarded prefixes should be tested according to real deployment; never write `startsWith("/api/admin")` manually when path segment boundaries are needed.

Requests containing `%2e`, `%2f`, `//`, or unusual characters may receive 400/404 from WebFlux/proxies/firewalls **before the security chain**. Do not force every rejected input to return 401/403; the invariant is **no out-of-policy request ever returns HTTP 200 with sensitive data**.

## 6. Distinguishing 401/403/404/302 across multiple chains

| Status | Typical meaning | Proves the right chain ran? |
| --- | --- | --- |
| 200 | Request handled | No, must check marker/identity |
| 401 | Missing/invalid Authentication | No, could be another chain or upstream |
| 403 | Authenticated lacking privilege, or CSRF/security denial | No, needs marker and cause |
| 404 | No handler/resource | **No**, can happen when no chain matched |
| 302 | Redirect, e.g., formLogin | No; check auth mechanism and chain |
| 400 | Malformed request | May come from parser/firewall before security chain |

In the demo, all chains enable HTTP Basic and disable `formLogin`, so protected GETs never redirect to HTML. The 401 (Basic challenge) and 403 (AccessDenied) mechanisms are distinct. Never omit Basic credentials in a test and use a CSRF 403 to claim a role rule executed.

## 7. Java 17+ / Spring Boot WebFlux project

Structure:

```text
multi-chain-webflux/
├── settings.gradle
├── build.gradle
├── src/main/java/example/chains/ChainsApplication.java
├── src/main/java/example/chains/SecurityConfig.java
├── src/main/java/example/chains/ChainMarkerFilter.java
├── src/main/java/example/chains/ApiController.java
└── src/test/java/example/chains/MultipleChainsIntegrationTest.java
```

Uses **Spring Boot 3.5.16**, Java 17+, compatible Gradle 8.4+. `spring-boot-starter-webflux` is the Reactive stack; do not add Servlet MVC `spring-boot-starter-web`. The project needs no database, IdP, or external API. An in-memory user store supports testing Basic authentication.

### 7.1. `settings.gradle`

```groovy
rootProject.name = 'multi-chain-webflux'
```

### 7.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The `spring-boot-starter-test` dependency brings JUnit 5 and `WebTestClient` for real tests. `spring-security-test` is not needed when sending real HTTP Basic credentials to the server; `mockUser`/`mockJwt` may be used in separate controller or authorization suites, though mock credentials do not prove a real password/JWT decoder ran.

### 7.3. `ChainsApplication.java`

```java
package example.chains;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ChainsApplication.class, args);
    }
}
```

### 7.4. `ChainMarkerFilter.java`

```java
package example.chains;

import java.util.Objects;

import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ChainMarkerFilter implements WebFilter {

    public static final String HEADER = "X-Lab-Security-Chain";

    private final String chainName;

    public ChainMarkerFilter(String chainName) {
        this.chainName = Objects.requireNonNull(chainName);
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders().set(
                    HEADER, chainName);
            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
```

`ChainMarkerFilter` has **no** `@Component`/`@Bean` so WebFlux does not register it as a global `WebFilter` running outside the security chains. Each chain instantiates its own. `beforeCommit` ensures the response header is attached before the HTTP response commits; `doFinally` is normally too late to set headers. It never reads `Authorization`/`X-User` and never creates `Authentication`.

### 7.5. `SecurityConfig.java`

```java
package example.chains;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userStore(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/admin/**"))
                .authorizeExchange(ex -> ex
                        .anyExchange().hasRole("ADMIN"))
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .addFilterAt(
                        new ChainMarkerFilter("admin"),
                        SecurityWebFiltersOrder.FIRST)
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/**"))
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/api/public").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .addFilterAt(
                        new ChainMarkerFilter("api"),
                        SecurityWebFiltersOrder.FIRST)
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                // No securityMatcher:
                // default matcher catches remaining requests.
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .addFilterAt(
                        new ChainMarkerFilter("fallback"),
                        SecurityWebFiltersOrder.FIRST)
                .build();
    }
}
```

**Security review of this configuration:**

1. `adminChain` has `@Order(1)` and a dedicated matcher; it must win over `/api/**`.
2. `apiChain` has `@Order(2)`, permitting strictly `GET /api/public` and `GET /api/me`, denying everything else.
3. `fallbackChain` has `@Order(3)` and **no dedicated `securityMatcher`**.
4. Fallback allows only `GET /public/ping`, blocking `/hidden` even for users with `ROLE_ADMIN`.
5. HTTP Basic is verified by Spring Security via `MapReactiveUserDetailsService` + BCrypt; it never reads `X-Role`.
6. `formLogin` is intentionally disabled; Basic GETs do not redirect to a login page.
7. Neither CSRF nor global headers are disabled to "make tests run". The project has only GET controllers; POSTs must still be rejected.
8. The marker sits at `SecurityWebFiltersOrder.FIRST`, **not as a global `WebFilter`**.
9. Never reuse a mutable `ServerHttpSecurity` instance across beans; Spring injects a fresh parameter for each chain.
10. Authorization rules are evaluated inside the selected chain, with no fallback after a deny decision.

### 7.6. `ApiController.java`

```java
package example.chains;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> publicPing() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/public")
    public Mono<Map<String, String>> apiPublic() {
        return Mono.just(Map.of("kind", "api-public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("principal", p.getName()));
    }

    @GetMapping({
        "/api/admin/report",
        "/api/admin/public"
    })
    public Mono<Map<String, String>> adminReport() {
        return Mono.just(Map.of("result", "admin-ok"));
    }

    @GetMapping("/api/hidden")
    public Mono<Map<String, String>> hiddenApi() {
        return Mono.just(Map.of("secret", "api-secret"));
    }

    @GetMapping("/api/adminX/data")
    public Mono<Map<String, String>> closePrefix() {
        return Mono.just(Map.of("secret", "prefix-secret"));
    }

    @GetMapping("/hidden")
    public Mono<Map<String, String>> hiddenFallback() {
        return Mono.just(Map.of("secret", "fallback-secret"));
    }
}
```

**Why include hidden handlers?** `/api/hidden` and `/hidden` have real handlers yet **are not on the allowlist**. Tests seeing 403 prove the security rule blocked them, rather than 404 from a missing controller.

`/api/admin/public` has `public` in its name yet falls under the admin matcher, so it is not automatically opened. `/api/adminX/data` has a similar prefix without the `/api/admin/` segment, so it must enter `apiChain`.

Controller `me` reads the Spring Security-authenticated `Mono<Principal>`, never reading a self-asserted `X-User`. Never call `.block()` in WebFlux handlers.

## 8. Running curl to cross-check

Start the app:

```bash
gradle bootRun
```

User fixtures (local only):

```text
alice / alice-pass -> ROLE_USER
admin / admin-pass -> ROLE_USER + ROLE_ADMIN
```

### 8.1. Fallback public

```bash
curl -i http://localhost:8080/public/ping
```

Expected:

```http
HTTP/1.1 200 OK
X-Lab-Security-Chain: fallback
Content-Type: application/json

{"status":"ok"}
```

### 8.2. API public

```bash
curl -i http://localhost:8080/api/public
```

Expect 200, `X-Lab-Security-Chain: api`, JSON `kind=api-public`.

### 8.3. Private API

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/me
```

Anonymous request: 401, marker `api`. Alice request: 200, marker `api`, JSON `principal=alice`.

### 8.4. Admin overlap

```bash
curl -i -u alice:alice-pass \
  http://localhost:8080/api/admin/report

curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/report
```

Alice: 403, marker **admin**; admin: 200, marker **admin**, body `result=admin-ok`. This demonstrates the high-priority chain is not shadowed by the broader API chain.

### 8.5. Fallback `denyAll` with a real handler

```bash
curl -i -u admin:admin-pass http://localhost:8080/hidden
```

Expect **403, marker `fallback`**, even though `admin` has `ROLE_ADMIN`. Only `GET /public/ping` is opened by the fallback.

### 8.6. Spoofed headers do not escalate privileges

```bash
curl -i -u alice:alice-pass \
  -H "X-User: admin" -H "X-Role: ADMIN" \
  http://localhost:8080/api/admin/report
```

Still returns 403, marker `admin`, because the real authenticated user is Alice.

### 8.7. POST to a GET-only public path

```bash
curl -i -u alice:alice-pass -X POST \
  http://localhost:8080/api/public
```

Expect 403. The failure may come from CSRF before authorization, or `denyAll`; to pinpoint the cause, test CSRF tokens/matchers separately rather than guessing from the status.

**Warning:** Basic credentials in HTTP are only Base64-encoded, not encrypted in transport. This demo is restricted to localhost; production mandates HTTPS/TLS, secret management, rate limiting, and never logging raw `Authorization`/`Cookie` headers. Bash uses backslashes for line continuation; on Windows use `curl.exe` or adjust shell syntax.

## 9. `WebTestClient` integration tests

`@SpringBootTest(webEnvironment=RANDOM_PORT)` launches the WebFlux app with real Spring Security. `@AutoConfigureWebTestClient` injects a `WebTestClient`. Tests send real Basic credentials, verifying `PasswordEncoder`, `SecurityWebFilterChain`, `securityMatcher`, `authorizeExchange`, 401/403, and marker headers.

If you only unit-test controller methods or use `mockUser()` for everything, you can bypass the authentication pipeline and miss real chain-ordering bugs. Mock users remain useful for isolated authorization unit tests, while this lesson requires **integration-level requests**.

### 9.1. `MultipleChainsIntegrationTest.java`

Path: `src/test/java/example/chains/MultipleChainsIntegrationTest.java`

```java
package example.chains;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MultipleChainsIntegrationTest {

    @Autowired
    WebTestClient client;

    private static final String CHAIN_HEADER =
            ChainMarkerFilter.HEADER;

    @Test
    void fallbackPublicWorksAndIsSelected() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback")
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void apiPublicUsesApiChain() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectBody()
                .jsonPath("$.kind").isEqualTo("api-public");
    }

    @Test
    void apiPrivateAnonymousGets401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void apiPrivateAliceGets200() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice");
    }

    @Test
    void apiInvalidBasicPasswordGets401() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void adminAnonymousGets401InAdminChain() {
        client.get().uri("/api/admin/report")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void adminRouteDeniesAliceWith403() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void adminRouteAllowsAdminWith200() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin")
                .expectBody()
                .jsonPath("$.result").isEqualTo("admin-ok");
    }

    @Test
    void adminPublicLookingNameIsStillProtected() {
        client.get().uri("/api/admin/public")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void forgedRoleCannotElevateAliceInAdminChain() {
        client.get().uri("/api/admin/report")
                .headers(h -> {
                    h.setBasicAuth("alice", "alice-pass");
                    h.set("X-User", "admin");
                    h.set("X-Role", "ADMIN");
                })
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }

    @Test
    void forgedUserDoesNotChangeApiPrincipal() {
        client.get().uri("/api/me")
                .headers(h -> {
                    h.setBasicAuth("alice", "alice-pass");
                    h.set("X-User", "admin");
                })
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(CHAIN_HEADER, "api")
                .expectBody()
                .jsonPath("$.principal").isEqualTo("alice");
    }

    @Test
    void existingApiHandlerIsDenied() {
        client.get().uri("/api/hidden")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void nearAdminPrefixBelongsToApiChain() {
        client.get().uri("/api/adminX/data")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void existingFallbackHandlerIsDenied() {
        client.get().uri("/hidden")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void unknownUrlIsAlsoHandledByFallback() {
        client.get().uri("/missing")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void fallbackAnonymousHiddenHandlerRequiresAuthentication() {
        client.get().uri("/hidden")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void headDoesNotInheritGetOnlyPublicRule() {
        client.head().uri("/api/public")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void postToGetOnlyPathIsNotOpened() {
        client.post().uri("/api/public")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(CHAIN_HEADER, "api");
    }

    @Test
    void fallbackDenyAllAlsoBlocksAdminUser() {
        client.get().uri("/hidden")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        CHAIN_HEADER, "fallback");
    }

    @Test
    void noCredentialPlusFakeAdminHeadersIsStill401() {
        client.get().uri("/api/admin/report")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(CHAIN_HEADER, "admin");
    }
}
```

### 9.2. Running the tests

```bash
gradle test
```

The code **designs 20 JUnit tests**. The expectation is `BUILD SUCCESSFUL` and 20 tests PASS with compatible JDK/Gradle/dependencies. This is **not a claim that Gradle was actually executed** while authoring the lesson. All HTTP Basic credentials are strictly local fixtures.

### 9.3. What the test suite proves

| Test group | Proves |
| --- | --- |
| Public fallback and API | Two anonymous URLs receive 200 in **two distinct chains** |
| Private API anonymous and Alice | 401/200; `api` marker and verified principal |
| Wrong Basic password | 401; self-asserted headers are not treated as login |
| Admin overlap | Alice 403, Admin 200, **`admin`** marker, not shadowed by API chain |
| Public-looking path in admin zone | Route name does not override admin matcher |
| Fake `X-User`/`X-Role` | Does not grant `ROLE_ADMIN` or change Alice's principal |
| Existing API handler not allowlisted | 403 and `api` marker |
| `adminX` prefix | Enters `apiChain` instead of `adminChain` |
| Existing fallback handler | Denied with 403 even though controller could return data |
| Fallback URL without handler | Still 403 for authenticated user, showing policy runs before handler lookup |
| HEAD/POST to GET-only | Not made public merely by sharing the path |
| Admin user on fallback | Still `denyAll`, no global override privilege |
| Anonymous on fallback | Basic entry point can return 401 |
| Chain identification via header | Does not rely solely on 401/403 status |

### 9.4. Never use 404 as proof of protection

If `GET /missing` returns 404, that can simply mean no handler exists, even if **no chain matched**. That is why a real `/hidden` handler is needed and tested to be blocked by the fallback `denyAll`. `unknownUrlIsAlsoHandledByFallback` supplements route coverage verification, but **does not replace** testing a real handler.

### 9.5. Debugging failures in order

If a test fails:

1. Check HTTP method, path, and Basic credentials in the test.
2. Read `X-Lab-Security-Chain`: admin/api/fallback? Is the marker present?
3. Wrong marker -> check `@Order` and `.securityMatcher(...)`.
4. Right marker but wrong 200/403 -> check `.authorizeExchange(...)` and authorities.
5. Wrong Basic yet 200 -> check auth manager/mocked security/chain selection.
6. POST 403 -> check CSRF before concluding the matcher hit `denyAll`.
7. 302 -> a chain may have `formLogin`/redirect enabled.
8. 404 -> handler may not exist or request was blocked before the chain; never treat 404 as QA pass.
9. Missing marker -> HTTP parser, firewall, gateway, CORS, or chain registration error; isolate by layer.
10. Never fix by removing the fallback, disabling Spring Security, or changing `denyAll` to `permitAll`.

### 9.6. Why not just read `@Order` on beans?

A code review seeing `adminChain @Order(1)` can still miss:
- A typo in matcher `/api/administration/**`.
- Another bean with `@Order(0)` matching everything.
- A fallback declared at too high a priority.
- A global `WebFilter` or HTTP proxy rewriting paths.
- Tests not wiring the full Spring Security infrastructure.
- A new URL falling outside every matcher.

Integration tests sending real requests and checking markers directly catch these issues far better than asserting bean definitions alone.

## 10. Testing boundaries beyond the sample

### 10.1. Trailing slashes and encoded paths

Add a case matrix tailored to your proxy/framework for:
- `/api/admin`, `/api/admin/`, `/api/admin/report`.
- `/api/adminX/data`, `/api/administrator/report`.
- Encoded slashes/dots, `//`, case variations, trailing slashes.
- Context path, base path, forwarded prefix if behind a load balancer.

**Do not** assume every encoded path must return 401/403. A malformed request may be rejected by the HTTP parser/firewall with 400/404 before reaching the Spring Security chain. The invariant is that no out-of-policy request ever receives sensitive data with HTTP 200.

### 10.2. Method restrictions

When a public rule allows only GET, test HEAD, POST, PUT, and DELETE on URLs with potential state changes. POST tests must account for CSRF separately. For token-based JSON REST APIs, CSRF rules may differ; disable CSRF only when the threat model allows and test all state-changing methods thoroughly.

### 10.3. CORS and OPTIONS

`OPTIONS` preflights may be handled by the CORS `WebFilter` before authentication/authorization. If chains A and B declare different CORS configs, browsers may fail while `curl` GET succeeds. Test `Origin`, `Access-Control-Request-Method`, `allow-origin`, `allow-credentials`, and preflight status per chain. Never blindly reflect `Origin` or return wildcard origins with credentials.

### 10.4. Framework-generated login endpoints

When enabling `formLogin`, `oauth2Login`, OAuth2 authorization code callbacks, logout, or request caches, several endpoints belong to the security framework with no user-written controller. If those endpoints lie **outside the `securityMatcher` of the chain** that needs them, the flow can return 404 or hit the wrong fallback.

This demo intentionally uses HTTP Basic only and disables `formLogin` in all three chains so there are no unaccounted-for login/redirect pages. In real systems, test login callbacks/logout/session renewal together with the chain's matcher and CSRF.

### 10.5. `SecurityContext` repository and sessions

Splitting into multiple chains does not automatically isolate user/session stores. The same `WebSession` can carry `SecurityContext` when using session-based auth, though permissions remain governed by the selected chain and its authorization rules. When tenant/session isolation is needed, design separate authentication, repositories, and trust boundaries rather than relying on `@Order`.

### 10.6. Using OAuth2 Bearer JWT for the API chain

A common production design:
- `/api/**` -> OAuth2 Resource Server JWT, Bearer challenge.
- `/portal/**` -> form login/`WebSession`.
- catch-all -> `denyAll`, explicitly opening only required health/asset routes.

Snippet replacing the auth mechanism in the API chain (requires `spring-boot-starter-oauth2-resource-server`, trusted `ReactiveJwtDecoder`, issuer/audience/expiry validators, and dedicated tests):

```java
@Bean
@Order(1)
SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth -> oauth
            .jwt(Customizer.withDefaults()))
        .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
        .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
        .build();
}
```

This is an **alternative snippet**, not added to the Basic project above. Spring Security Test's `mockJwt()` is useful for testing authorities/routes, yet **can bypass the decoder**. To verify real JWT handling, add signed JWT/JWKS tests covering signature, issuer, audience, expiry, and scope cases. Keep the chain selection tests and update credential/header expectations.

## 11. Common mistakes

| Mistake | Impact | Remedy |
| --- | --- | --- |
| `apiChain` higher priority than `adminChain` | Broad chain shadows admin | `@Order` narrow before broad + overlap test |
| Missing catch-all fallback | URLs outside matchers lack Spring Security protection | Fallback with no dedicated matcher |
| Fallback `anyExchange().permitAll()` | New endpoints unexpectedly public | `denyAll` + explicit allowlist |
| Assuming 403 tries the next chain | Misunderstood chain selection | First matching chain wins |
| Using `pathMatchers` instead of `securityMatcher` to pick chains | Chain may match all URLs | Use the right matcher layer |
| Treating 404 as security blocking | May just be a missing handler | Test a real handler getting denied |
| Asserting only 200 | Misses authorization bypasses | Test 401/403 and markers |
| Not testing similar prefixes | May match wrong segment | `PathPatternParser` + boundary tests |
| Forgetting HTTP methods | HEAD/POST accidentally public | Method-specific allowlists |
| Disabling CSRF so POST doesn't 403 | Loses browser protection | Explicit CSRF policy/tests |
| Using Servlet `HttpSecurity` in WebFlux | Wrong stack | `ServerHttpSecurity` |
| Treating `X-User`/`X-Role` as authorities | Privilege escalation | Verified `Authentication` |
| Marker `WebFilter` both global and `addFilterAt` | Duplicate/wrong chain headers | Keep marker strictly inside chains |
| Not checking Basic challenge | 302 or 403 instead of 401 | Test auth mechanism per chain |
| Switching fallback to `authenticated` | Logged-in users access uninventoried URLs | Use `denyAll` for fail-closed |
| Not testing login/callback endpoints | 404 or wrong chain | Include framework endpoints in matchers |
| Testing mock users and claiming passwords work | Bypasses real auth in tests | Real Basic `WebTestClient` tests |
| Switching to JWT while using only `mockJwt` | Signature validation untested | Real signed token/JWKS tests |
| Exposing lab chain header in production | Fingerprints internals | Remove before deployment |
| Forgetting to update tests when changing chain priorities | Silent mis-authorization | Review matrix + CI tests |

## 12. Pre-production QA checklist

1. List every `SecurityWebFilterChain` bean, matcher, and `@Order`.
2. Place narrow, sensitive matchers before broad matchers.
3. Have a no-`securityMatcher` fallback last, `denyAll` except intentional public routes.
4. Distinguish chain selection from authorization rule selection.
5. Test overlapping routes to confirm they hit the right high-priority chain.
6. Test near-matching prefixes so they do not fall into the wrong chain.
7. Test the fallback against a **real** disallowed handler.
8. Test 401 for anonymous/bad credentials and 403 for authenticated lacking role.
9. Test valid users/roles receiving 200 on the intended chain.
10. Test HTTP methods other than GET on public paths.
11. Test CSRF/CORS/preflight if browser credentials are used.
12. Test security headers and redirect/login/logout endpoints per chain.
13. Test URL normalization, proxy path rewriting, base paths, and encoded paths in staging.
14. Never rely on 404 as proof of authorization.
15. Never trust user/role from raw headers or query parameters.
16. Rely on verified `Principal` and verified role policies.
17. If using JWT, validate issuer/audience/signature/expiry—not just `mockJwt`.
18. Never register a debug `WebFilter` globally when observing a single chain.
19. Strip lab-only response markers in production.
20. When upgrading Spring versions, re-run the full test matrix and check release security advisories.

## 13. Exercises and short answers

1. Why must `/api/admin/**` take priority over `/api/**`? — Because the two matchers overlap and the first matching chain wins.
2. If `adminChain` returns 403, is `apiChain` tried next? — No.
3. How does `securityMatcher` differ from `pathMatchers`? — One selects the chain; the other authorizes requests inside the chain.
4. Does `anyExchange()` cover the whole app? — Only all remaining requests in the selected chain.
5. What is the role of a fallback with no matcher? — Covering requests that matched no earlier chain.
6. Why is fallback `denyAll` better than `authenticated` in a fail-closed policy? — `authenticated` opens every new endpoint to logged-in users.
7. What can happen if a fallback is missing? — Some URLs are left unprotected by any Spring Security web chain.
8. Why isn't checking 404 enough? — A missing controller also returns 404 when no security exists.
9. Is the marker header a production security header? — No, strictly for labs/tests.
10. Which test catches chains A and B being swapped? — `GET /api/admin/report` with Alice/Admin and expected `admin` marker.
11. Which chain should `/api/adminX/data` use? — The API chain.
12. `/api/hidden` has a handler, so can Basic Alice call it? — No, API `anyExchange` `denyAll` -> 403.
13. Can Admin call `/hidden`? — No, fallback `denyAll` -> 403.
14. Does public GET mean public POST? — No, if the rule restricts to `HttpMethod.GET`.
15. Where can a POST 403 come from? — CSRF or authorization.
16. Why doesn't `X-Role: ADMIN` change permissions? — Client-supplied headers are unverified.
17. How does `@Order` differ from `SecurityWebFiltersOrder`? — Selecting a chain vs ordering a `WebFilter` inside a chain.
18. With JWT, does `mockJwt()` test real signatures? — No.
19. Why must form login endpoints be accounted for in chain matchers? — The framework generates login/callback routes that could otherwise be blocked by the fallback.
20. If a request has no marker, what can you conclude? — Not enough by itself; it may have been blocked before the chain and needs investigation.
21. Does HTTP Basic encrypt passwords over HTTP? — No, TLS is required.
22. Why use a real `/hidden` handler in tests? — To prove the fallback protects real resources.
23. What if neither `@Order(1)` nor `@Order(2)` matches a URL? — The fallback is evaluated.
24. Why don't multiple chains automatically isolate `WebSession`? — They are policy/filter paths, not separate session stores by default.
25. Which test outcome is expected when wrong Basic credentials hit `/api/me`? — 401 and `api` marker.

## 14. References

- Spring Security 6.5 — WebFlux Security, Multiple Chains Support: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security — Reactive Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security — WebTestClient Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Reactive HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/passwords/basic.html
- Spring Security 6.5 Javadoc — ServerHttpSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 Javadoc — PathPatternParserServerWebExchangeMatcher: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html
- Spring Security 6.5 Javadoc — SecurityWebFilterChain: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html
- Spring Boot 3.5 — Gradle plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Conclusion:** In Spring Security Reactive, multiple `SecurityWebFilterChain`s require two verification layers: (1) requests enter the **right chain** per `@Order` + `securityMatcher`; (2) that chain **authorizes properly** per `authorizeExchange`. Always place narrow matchers before broad ones, keep a catch-all `denyAll` fallback, and test with `WebTestClient` using 200/401/403, real handlers, overlapping path prefixes, and a test-only debug marker. A 404 does not prove a chain protects an endpoint, and a 403 does not by itself prove the right chain was chosen.