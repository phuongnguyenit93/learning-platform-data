# Multiple SecurityWebFilterChain Beans with @Order and the First-Match-Wins Principle

> **Module:** Spring Security - reactive · **Parent topic:** Security configuration  
> **Goal:** Know when to split a security configuration into multiple `SecurityWebFilterChain` beans in Spring WebFlux, understand `@Order` precedence accurately, `securityMatcher` scope, and the consequences when two chains match the same request. Includes a Java 17+ example using Reactive Spring Security, HTTP Basic, WebTestClient tests, and a misconfiguration scenario leading to overly broad access.

## 1. The problem: one application, multiple security zones

A WebFlux application may have areas requiring different policies:

- `GET /api/status`: public API health check, no login required.
- `GET /api/profile`: regular API, requires an authenticated account.
- `GET /api/admin/report`: administrative API, requires the `ADMIN` role.
- `GET /health`: public health check endpoint.
- All other paths: must not allow access automatically.

All of this can be expressed in **one chain** with multiple rules. However, when areas need different login mechanisms, filters, error handling, CSRF settings, or scopes, Reactive Spring Security lets you declare **multiple `SecurityWebFilterChain` beans**. Each bean describes an independent security chain.

Key question: if `GET /api/admin/report` matches both `/api/admin/**` and `/api/**`, will Spring Security apply both chains, merge their permissions, or choose one chain?

**Answer:** Spring Security evaluates chains in priority order and **selects the first chain whose `securityMatcher` matches the request**. Only the selected chain processes the request; it does not fall through to lower-priority chains to "add" or "re-check" permissions. Therefore, `@Order` directly impacts security.

## 2. Separating two phases: selecting the chain vs. authorizing inside the chain

Two questions must be clearly distinguished.

| Phase | Relevant API | Question | Outcome |
| --- | --- | --- | --- |
| **Select chain** | `ServerHttpSecurity.securityMatcher(ServerWebExchangeMatcher)` | Which security chain is responsible for this request? | Picks the **first** matching chain by `@Order` |
| **Authorize inside chain** | `authorizeExchange(...).pathMatchers(...)/anyExchange()` | Does the request in the chosen chain have sufficient permissions? | Allow, challenge for authentication, or deny |
| **Execute endpoint** | Router/controller, service, repository | If permitted, which endpoint and data are processed? | Response / business logic |

**`securityMatcher` defines the scope of the entire chain.** `pathMatchers` inside `authorizeExchange` only govern **permissions within the selected chain**. Putting `pathMatchers("/api/admin/**")` inside the general API chain does not give that chain higher priority.

Visualization:

~~~mermaid
flowchart TD
    R["HTTP request"] --> A{"Chain @Order(1): /api/admin/** ?"}
    A -->|"Matches"| AA["Select ADMIN chain → check ROLE_ADMIN"]
    A -->|"No"| B{"Chain @Order(2): /api/** ?"}
    B -->|"Matches"| BB["Select API chain → public / authenticated rules"]
    B -->|"No"| C{"Chain @Order(3): all requests?"}
    C -->|"Matches"| CC["Select FALLBACK chain → /health public; rest denyAll"]
    C -->|"No"| D["No chain selected: risk of missing protection"]
    AA --> E["Allow / deny decision; DO NOT run next chain"]
    BB --> E
    CC --> E
~~~

In the example we are about to build, the last chain **does not** call `securityMatcher`, so it uses the default matcher that matches all remaining requests. As a result, every request has a chain responsible for it. A configuration with only path-restricted chains and no catch-all can leave unmatched requests outside those security chains. Do not treat this as a way to create public endpoints: use `permitAll()` in an appropriate chain so the policy stays explicit.

## 3. Exact meaning of @Order

Spring evaluates `SecurityWebFilterChain` beans in the order managed by Spring:

- **Smaller `@Order` values are evaluated first**: `@Order(1)` precedes `@Order(2)`, then `@Order(3)`.
- `Ordered.HIGHEST_PRECEDENCE` is a constant representing the highest priority; you do not need it if values 1, 2, 3 are already clear and unique.
- `@Order` is placed on the `@Bean` method declaring the chain. Do not rely on the order methods appear in the Java file or bean registration order.
- Choose **distinct, explicit** order values for chains with overlapping matchers. If two chains have the same priority, never rely on accidental ordering to guarantee security.
- `@Order` does not mean a chain "has stronger permissions"; it only decides **the order in which chains are tried**. Actual permissions live in the authorization rules of the selected chain.

**Safe rule for overlapping paths:** a more specific matcher must be evaluated **before** a broader matcher, for example:

| Chain | `@Order` | `securityMatcher` | Policy |
| --- | --- | --- | --- |
| Admin | 1 | `/api/admin/**` | `hasRole("ADMIN")` |
| General API | 2 | `/api/**` | `/api/status` public, other APIs require login |
| Fallback | 3 | Default match-all | `/health` public, rest denied |

A request `GET /api/admin/report` matches all three scopes, but **only the Admin chain** is selected because it has the highest priority.

## 4. Building a Spring Boot WebFlux example

This example uses Java 17+ and Spring Security 6.x via Spring Boot 3.3.x to focus on the chain selection API. For new projects, choose a currently supported Spring Boot/Spring Security version; do not treat demo versions as production security defaults. This sample code lives in a standalone Maven project; it does not use Servlet MVC APIs.

Structure:

~~~text
multi-reactive-chains/
├── pom.xml
└── src/
    ├── main/java/demo/multichain/
    │   ├── MultiChainApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/multichain/
        └── MultiChainSecurityTest.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-reactive-chains</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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

`spring-boot-starter-webflux` brings in WebFlux and Reactor; `spring-boot-starter-security` brings in Spring Security; `spring-boot-starter-test` supports Spring Test/JUnit 5/WebTestClient. Do not add `spring-boot-starter-web` to the example, to avoid switching the app to Servlet MVC since Spring Boot prefers MVC when both web starters are present.

### 4.2. Entry point

File `src/main/java/demo/multichain/MultiChainApplication.java`:

~~~java
package demo.multichain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiChainApplication.class, args);
    }
}
~~~

### 4.3. Configuring three SecurityWebFilterChain beans

File `src/main/java/demo/multichain/SecurityConfig.java`:

~~~java
package demo.multichain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    // Most specific chain: handles only /api/admin/**
    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/admin/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    // Broader chain: only tried when adminChain does not match.
    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**")
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/status").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    // Catch-all: protects all requests outside the two zones above.
    @Bean
    @Order(3)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails member = User.withUsername("member")
            .password(passwordEncoder.encode("member-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(member, admin);
    }
}
~~~

**How to read the code correctly:**

1. `@EnableWebFluxSecurity` enables WebFlux security. Each `@Bean` method returns a **separate chain** with its own matcher, authorization, and HTTP Basic setup. `ServerHttpSecurity` is configured per bean and finalized with `build()`.
2. `adminChain` has matcher `/api/admin/**` and priority 1. Once a request matches, `anyExchange().hasRole("ADMIN")` means **every request within the Admin chain's scope** must carry the `ROLE_ADMIN` authority. It does not mean every path in the whole application needs ADMIN.
3. `apiChain` has matcher `/api/**` and priority 2. It is evaluated when the Admin chain does not match. `GET /api/status` is opened via `permitAll()`; the rest of the API requires `authenticated()`.
4. `fallbackChain` attaches no specific `securityMatcher`, so it receives the remaining requests; `GET /health` is public and all other requests hit `denyAll()`. This is a deny-by-default choice so unconfigured URLs do not slip through.
5. `httpBasic(Customizer.withDefaults())` enables HTTP Basic in each chain to demonstrate a shared user store. `formLogin(...disable)` prevents redirecting API requests to an HTML login page instead of returning an HTTP Basic challenge.
6. The `member` account has `ROLE_USER`; `admin` has `ROLE_ADMIN`. They are strictly for learning on localhost; demo passwords are encoded via `PasswordEncoder` when building the in-memory users. Never hardcode fixed credentials in production source code.
7. The example **keeps CSRF enabled** by default: the GET APIs here are read operations. When adding POST/PUT/DELETE, CSRF can affect status codes; decide based on how clients carry credentials rather than disabling CSRF everywhere just to make tests pass.
8. **Chain selection** order lives in `@Order` and `securityMatcher`. **In-chain permission** order lives in `authorizeExchange` rules. These are two independent layers.

Do not treat `.anyExchange()` in two different chains as overriding each other. Each rule exists only within its own selected chain. Conversely, placing `.anyExchange()` early inside the same rule list can shadow specific rules placed after it.

## 5. Controller to verify which chain is selected

File `src/main/java/demo/multichain/DemoController.java`:

~~~java
package demo.multichain;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/api/status")
    public Mono<Map<String, String>> apiStatus() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "username", context.getAuthentication().getName()
            ));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> adminReport() {
        return Mono.just(Map.of("report", "admin-only"));
    }

    @GetMapping("/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }

    @GetMapping("/internal/ping")
    public Mono<Map<String, String>> internalPing() {
        return Mono.just(Map.of("status", "hidden"));
    }
}
~~~

`internalPing()` intentionally exists to prove that **having a handler does not mean a request is allowed to reach it**. `/internal/ping` enters the fallback chain; `anyExchange().denyAll()` prevents the endpoint from running even when the client sends valid credentials.

Responses use fixed `Map<String,String>` data, so no database is needed. For profile, the principal is read via `ReactiveSecurityContextHolder` inside the reactive pipeline. Do not use `ThreadLocal` as commonly assumed in Servlet MVC.

## 6. Detailed trace of each request

### Case A: GET /api/admin/report as member

1. Admin matcher `/api/admin/**` matches.
2. Admin chain is **selected immediately**; API chain and fallback are not evaluated.
3. HTTP Basic authenticates `member` successfully, but the user only has `ROLE_USER`.
4. Rule `hasRole("ADMIN")` denies access → expected **403 Forbidden**.
5. Spring Security **does not try `apiChain` next**, even though `apiChain` has `anyExchange().authenticated()` and `member` is logged in.

This is the most important proof: if security ran chains in a "keep trying until granted" manner, `member` would slip into admin. Spring Security does not work that way.

### Case B: GET /api/profile as member

1. Admin chain does not match.
2. API chain matches `/api/**` and is selected.
3. Does not match public path `GET /api/status`, so reaches `anyExchange().authenticated()`.
4. Valid HTTP Basic creates `Authentication` for `member` → controller returns username, expected **200 OK**.

### Case C: GET /api/status without credentials

1. Admin does not match, API matches.
2. Rule `permitAll()` allows anonymous access → **200 OK**.
3. The endpoint does not need to inspect/read `SecurityContext` itself.

`permitAll()` does not promise to bypass every authentication filter. If a client deliberately sends a **bad** Basic header, the filter may return 401 before reaching the public result; testing "public" access must be done with requests **carrying no credentials**.

### Case D: GET /health without credentials

Neither specific matcher matches. Fallback receives the request; `GET /health` allows anonymous access → **200 OK**.

### Case E: GET /internal/ping as member

Admin and API do not match. Fallback receives the request; `denyAll()` rejects even an authenticated user → expected **403 Forbidden**. There is no "next fallback" because this is the last chain.

## 7. Route, matcher, chain, and outcome matrix

| Request | First matching chain | Authorization condition | Expected outcome |
| --- | --- | --- | --- |
| `GET /api/status`, anonymous | API (2) | `permitAll()` | 200 |
| `GET /api/profile`, anonymous | API (2) | `authenticated()` | 401 |
| `GET /api/profile`, member | API (2) | Authenticated | 200 |
| `GET /api/admin/report`, anonymous | Admin (1) | Unauthenticated for ADMIN rule | 401 |
| `GET /api/admin/report`, member | Admin (1) | Missing `ROLE_ADMIN` | 403 |
| `GET /api/admin/report`, admin | Admin (1) | Has `ROLE_ADMIN` | 200 |
| `GET /health`, anonymous | Fallback (3) | `permitAll()` | 200 |
| `GET /internal/ping`, member | Fallback (3) | `denyAll()` | 403 |

Expected outcomes apply to the **example's HTTP Basic configuration**. If a project replaces HTTP Basic with form login/OAuth2/JWT, the entry point and responses may differ. Do not rely solely on status codes to reverse-infer which chain was selected without inspecting matchers and authentication configuration.

## 8. Automated testing with WebTestClient

File `src/test/java/demo/multichain/MultiChainSecurityTest.java`:

~~~java
package demo.multichain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MultiChainSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicApiWorksWithoutCredentials() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void apiProfileRejectsAnonymous() {
        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void normalUserCanViewProfile() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("member", "member-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("member");
    }

    @Test
    void normalUserCannotEnterAdminChain() {
        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("member", "member-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanEnterAdminChain() {
        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("admin-only");
    }

    @Test
    void healthIsHandledByFallback() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("UP");
    }

    @Test
    void fallbackDeniesInternalRouteEvenWhenAuthenticated() {
        client.get().uri("/internal/ping")
            .headers(h -> h.setBasicAuth("member", "member-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRouteRejectsAnonymous() {
        client.get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Run inside the directory containing `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

The tests call the real application on a random port and pass through the security filters. They verify the combined effect of chain selection and authentication/authorization. Do not invoke the controller directly via `new DemoController()` to "test `SecurityWebFilterChain`" because direct calls bypass HTTP security.

**The most valuable test is** `normalUserCannotEnterAdminChain()`: it guards against regressions when someone accidentally reorders chains or broadens a `securityMatcher`. Even though `member` is valid for the general API, they are still rejected in the admin area.

The example uses in-memory users for ease of testing. A project with its own database or identity provider must configure the corresponding authentication method, permissions, and test fixtures; never assume the example user data represents a real system's authorization mechanism.

## 9. Manual testing with curl

Start the application, then test from another terminal. In PowerShell 5.1, use `curl.exe` to avoid the `curl` alias.

**Public API:**

~~~bash
curl -i http://localhost:8080/api/status
~~~

Expected HTTP 200 and body:

~~~json
{"status":"ok"}
~~~

**API requiring login, anonymous call:**

~~~bash
curl -i http://localhost:8080/api/profile
~~~

Expected HTTP 401 (typically with `WWW-Authenticate: Basic ...`).

**Member accessing profile:**

~~~bash
curl -i -u member http://localhost:8080/api/profile
~~~

curl prompts for the password; enter `member-pass`. Expected HTTP 200 and:

~~~json
{"username":"member"}
~~~

**Member accessing admin, blocked:**

~~~bash
curl -i -u member http://localhost:8080/api/admin/report
~~~

Enter `member-pass`; expected HTTP 403 because the request stops at **adminChain**; it is not forwarded to `apiChain` to try a looser rule.

**Admin accessing admin:**

~~~bash
curl -i -u admin http://localhost:8080/api/admin/report
~~~

Enter `admin-pass`; expected HTTP 200:

~~~json
{"report":"admin-only"}
~~~

**Fallback:**

~~~bash
curl -i http://localhost:8080/health
curl -i -u member http://localhost:8080/internal/ping
~~~

The first command expects 200; for the second, enter `member-pass` and expect 403.

In real environments, HTTP Basic must run over **HTTPS**: Base64 encoding is not security encryption. Avoid placing real passwords directly in command history. The users/passwords above are for localhost only.

## 10. Dangerous failure case: reversing chain order

Suppose a developer accidentally swaps the order as follows (purely an **error illustration**, do not apply):

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/admin/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().hasRole("ADMIN")
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

`GET /api/admin/report` matches both matchers. The API chain has `@Order(1)` so it is selected **first**, applying `authenticated()`. The `member` user has a valid account, so they **pass the security-layer check** and can reach the admin controller unless other safeguards exist. The Admin chain with its stricter role requirement is **never used** for that request.

This is a **chain shadowing** bug: a broader matcher "shadows" a specific matcher. It can expose administrative functionality even though each chain looks correct when read in isolation.

**Proper fix:** give `adminChain` higher priority than `apiChain`, or design **non-overlapping** matchers and explicitly test excluded paths. Never expect a `hasRole("ADMIN")` rule in a lower-priority chain to supplement an already chosen chain.

## 11. Another failure case: first chain without a securityMatcher

Another mistake:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain broadChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

If this method is placed before the Admin/API chains and **has no specific `securityMatcher`**, it matches every request. Later chains never get a chance to process any path. Some endpoints will unexpectedly prompt for login; worse, endpoints needing special roles may fall under an overly broad `authenticated()` rule.

**Rule of thumb:** put the catch-all last; write tests for overlapping paths; verify each chain's matcher during code review.

## 12. Missing fallback: creating a protection gap

If you only declare:

~~~java
.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**")
)
~~~

and no other chain receives `/internal/**`, requests outside `/api/**` may **not be processed by any SecurityWebFilterChain**. If a handler exists, you could accidentally expose an endpoint without HTTP security-layer protection. Never assume "not matching a chain" automatically means `denyAll()`.

There are two ways to protect the design:

1. Use a fallback chain matching all remaining requests, placed last; explicitly configure `permitAll()` for public endpoints and `denyAll()` or `authenticated()` for the rest.
2. If you intentionally want security to apply only to a very narrow scope, treat that as a deliberate architectural decision; audit all other URLs and have tests confirming the out-of-scope area.

**Do not confuse `anyExchange().denyAll()` with a catch-all matcher.** `anyExchange()` only blocks requests **that have already entered that chain**. A chain with `securityMatcher("/api/**")` and `anyExchange().denyAll()` cannot block `/internal/ping` if that request never matched the chain's matcher.

## 13. Distinguishing two commonly confused types of ordering

### 13.1. Ordering of chains

~~~text
Request
  ├─ adminChain @Order(1), matcher /api/admin/**
  ├─ apiChain   @Order(2), matcher /api/**
  └─ fallback   @Order(3), default match-all matcher
                 → STOPS at the first matching chain
~~~

### 13.2. Ordering of rules inside one chain

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/status").permitAll()
    .anyExchange().authenticated()
)
~~~

Inside the API chain, the specific `/api/status` rule must be declared before the broad `anyExchange()` rule. If a general rule captures all requests first, specific rules after it may have no effect (or the configuration may be rejected by Spring Security).

The two ordering layers operate independently:

- `@Order` orders **chain beans**.
- `pathMatchers` order arranges **authorization rules inside one chain**.
- `securityMatcher` attaches scope to a chain.
- `anyExchange` attaches a fallback rule for **requests inside the chain**.

Learning to separate these two layers prevents misdirected fixes: when `/api/admin/report` slips through, check which chain was selected **before** editing rules inside a chain that may never have been invoked.

## 14. Using multiple chains to separate authentication mechanisms

The previous example used HTTP Basic for all three chains to focus on chain selection. In practice, each chain can use its own mechanism:

| Application area | Example matcher | Common mechanism | Additional checks needed |
| --- | --- | --- | --- |
| Resource Server API | `/api/**` | OAuth2 Bearer JWT | Signature, expiration, issuer, audience, scope |
| Admin web | `/admin/**` | Session + form login/OIDC | Role, MFA, session/CSRF |
| Internal service | `/internal/**` | Internal token or mTLS at gateway | Network policy, service identity |
| Fallback | Match-all | Policy-dependent | Do not leave out-of-scope paths open |

In Spring Security WebFlux, authentication configuration is set **per chain**. Configuring `oauth2ResourceServer(...jwt(...))` on the API chain does not mean another chain inherits that mechanism. When using JWT, you need a real decoder/issuer and separate tests for valid and invalid tokens. **Never merely decode the payload and trust its claims.**

If the app uses cookies/sessions for one area, evaluate CSRF appropriately for that area. If a stateless API uses client-attached Bearer headers and does not rely on cookies for authentication, you can consider disabling CSRF on the API chain according to your threat model. Never disable protection across the board just because another chain uses tokens.

CORS can also be configured differently per area, but **CORS does not replace authentication/authorization**. Multiple chains introduce multiple configuration points; test consistency of headers, login/logout, CSRF, exception handling, and CORS along real paths.

## 15. Diagnostic workflow when a route is wrongly allowed or denied

When a path returns an unexpected 200, 401, 403, or 404, follow this exact sequence:

1. Identify the actual **HTTP method + path**, including proxy/gateway prefixes and paths after reverse proxying. Query strings are not a substitute for matcher paths.
2. List all `SecurityWebFilterChain` beans and their `@Order` values; determine which chain is evaluated first.
3. Inspect each chain's **`securityMatcher`**; pinpoint the **first matching** chain. If no chain matches, that is a separate investigation branch.
4. In the selected chain, inspect the authentication mechanism: HTTP Basic, session, Bearer, or another mechanism. 401 can occur due to missing/invalid credentials.
5. Read `authorizeExchange` rules in order; 403 can result from being authenticated yet lacking a role/scope, or hitting `denyAll()`.
6. If authorization passes, check controller mapping, method security, and data/business authorization. 404 can come from the handler or a resource-hiding policy.
7. Verify with tests for **both allowed and blocked cases**; avoid drawing conclusions from a single response.

In test environments, you can use Spring Security logging at an appropriate level to observe matchers/filters. Never log plaintext passwords, full `Authorization` headers, access tokens, or personal data. When debugging behind a gateway, distinguish statuses returned by the gateway from those returned by the application itself.

### Investigation table template

| Symptom | Possible cause | Verification step |
| --- | --- | --- |
| USER can access `/api/admin/report` | Broad API chain has higher priority than Admin chain | Re-check `@Order` and overlapping matchers |
| `/api/status` returns 401 despite being public | Admin/fallback chain caught it first or client sent bad credentials | Identify the chain; retry without an `Authorization` header |
| `/health` returns 401 or 403 | Fallback rule lacks `permitAll()`, or another chain matched it | Check each chain's matcher and HTTP method |
| `/internal/ping` returns 200 | Missing fallback/catch-all or overly permissive config | Test both authenticated and anonymous for non-API paths |
| Valid Admin still gets 403 | Role mapped incorrectly, e.g., missing `ROLE_ADMIN` | Inspect actual `Authentication` authorities and `hasRole` |
| Later chains never run | High-priority chain has a match-all matcher | Add a narrow matcher to the first chain and move catch-all last |
| POST gets 403 while GET succeeds | CSRF or HTTP method rule | Cross-check CSRF policy, HTTP method, and how credentials are sent |

## 16. Design mistakes to avoid

- **Assuming chains stack cumulatively.** In reality **one** first-matching chain is chosen; authorization failure does not make Spring try the next chain.
- **Using `@Order` without `securityMatcher` on a high-priority chain.** That chain can capture every request, rendering subsequent chains useless.
- **Putting a broad matcher before a specific matcher.** `/api/**` can shadow `/api/admin/**`, bypassing ADMIN checks.
- **Having only specialized chains without a catch-all.** Other URLs may not be protected by any security chain.
- **Treating `pathMatchers` as chain selection.** Those are permission rules inside the chosen chain; chain selection uses `securityMatcher`.
- **Trusting a single 200 test.** You need tests for 401, 403, role-based access, and paths outside matchers, especially after config changes.
- **Copying Servlet APIs into WebFlux.** Use `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ServerWebExchangeMatcher`, not Servlet's `SecurityFilterChain` + `HttpSecurity`.
- **Disabling CSRF/CORS or opening all routes to "fix" a test.** Identify the chosen chain and the rejecting layer first; login policy and threat model drive security decisions.
- **Equating a role with business-data permissions.** `ROLE_ADMIN` on a route does not replace tenant, owner, transaction-state, or data-output controls.

## 17. Practice exercises

### Exercise 1 — Predict the chain before running

For the three chains in section 4, build a table showing the selected chain for:

- `GET /api/admin/report`
- `GET /api/profile`
- `GET /api/status`
- `GET /health`
- `GET /internal/ping`

Then write tests comparing your predictions with HTTP statuses. Present the **chain name first**, then explain permissions. Do not just guess status codes.

### Exercise 2 — Deliberately reproduce an ordering bug

In a copy of the lab, change only Admin's `@Order` from 1 to 2 and API's from 2 to 1. Re-run `normalUserCannotEnterAdminChain`. Predict what changes and explain why the request is handled by the API chain. Then restore the safe ordering.

Note: this change is strictly for a local lab and requires a test that catches the bug; never deploy a misconfiguration on systems with real data.

### Exercise 3 — Add a dedicated area

Add an endpoint `GET /api/reports/summary` requiring `ROLE_ANALYST`. You can choose between two designs:

1. Add a separate rule `pathMatchers(...).hasRole("ANALYST")` in the existing API chain when only permissions differ; or
2. Create a dedicated `/api/reports/**` chain with an `@Order` between Admin and API if this area genuinely needs different filters or authentication.

Explain why creating a new chain for every role is unnecessary and why anti-shadowing tests must be added whenever chains have overlapping matchers.

### Exercise 4 — Prove the fallback

Add `GET /unknown` in the controller without declaring an allowing rule. Verify that an authenticated user is rejected by the fallback. Then allow `GET /public-news` with `permitAll()` in the fallback while keeping `denyAll()` for all remaining paths.

### Completion criteria

- [ ] Correctly draw the two layers: `securityMatcher` selects the chain; `authorizeExchange` decides permissions.
- [ ] Explain why **`@Order(1)` precedes `@Order(2)`** and selects the first matching chain.
- [ ] Prove that `/api/admin/**` must be evaluated before `/api/**` when matchers overlap.
- [ ] Run the endpoints and tests in the WebFlux example.
- [ ] Have at least one negative test for MEMBER accessing ADMIN and one test for a fallback URL.
- [ ] Explain why `anyExchange().denyAll()` in the API chain does not automatically protect URLs outside `/api/**`.
- [ ] Distinguish HTTP 401, 403, and 404 routing errors without guessing the chain from status alone.
- [ ] State when to split into multiple chains and when one chain with multiple rules is enough.

## 18. Self-check questions

1. A request matches two `securityMatcher`s: does Spring Security run both or only the first chain? If the first chain returns 403, is the second chain tried?
2. Do `@Order(1)` and `@Order(2)` guarantee order when placed on any two chain bean methods in the same configuration?
3. What is the difference between `http.securityMatcher("/api/**")` conceptually and `authorizeExchange().pathMatchers("/api/**")`? (In WebFlux, `securityMatcher` typically takes a concrete `ServerWebExchangeMatcher` as shown in the example.)
4. If the first chain does not call `securityMatcher`, what happens to chains placed after it?
5. If there is no catch-all and a request does not belong to any chain matcher, does the application deny it by default?
6. Why does a test "member accessing `/api/admin/report` must get 403" catch ordering bugs that a test "admin gets 200" might miss?
7. When you need both a JWT API and a session web app, in which chain do you configure authentication, exception handlers, and CSRF?
8. If a route returns 403, how can you verify that it is an authorization failure in the selected chain rather than CSRF or another mechanism?

## 19. References

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): official example of `@Order`, `securityMatcher`, and first-match-wins chains.
- [Spring Security — Authorize HTTP Exchanges](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): access rules in a reactive chain.
- [Spring Security — HTTP Basic in WebFlux](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html): WebFlux Basic challenge and authentication.
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): impact on state-changing requests.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive web stack and controllers.

**Principle to remember:** **Chain selection decides "who is responsible for protecting this request", not an additive union of multiple policies.** Put specific matchers before general matchers, prioritize explicitly with `@Order`, and always include a tested fallback.