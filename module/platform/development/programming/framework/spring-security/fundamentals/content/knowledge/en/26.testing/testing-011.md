# Testing Endpoints Outside Expected Paths

> **Topic:** Spring Security — fundamentals / Testing. This guide verifies whether HTTP paths and methods **outside the allowed API list** (unexpected / unlisted endpoints) are blocked according to policy. Focuses on Spring Security on the **Servlet stack** with Java 17+, Spring Boot 3.x, and Spring Security 6.x; the complete example uses Spring Boot 3.5.0 and MockMvc.

## 1. Why are "unexpected" endpoints a security risk?

An application may intentionally expose `GET /public/ping`, let authenticated users read `GET /api/documents/{id}`, and allow only admins to read `GET /admin/report`. Yet during development, libraries, legacy modules, or routing configs can introduce endpoints such as:

- `GET /internal/diagnostics` — internal diagnostics exposing sensitive details.
- `GET /legacy/export` — a leftover data-export route from an older version.
- `GET /api/documents/101/export` — an extra operation sitting right next to an allowed API.
- `GET /admin/report/archive` — a URL sharing a prefix with a valid admin URL yet carrying different semantics.
- `POST /public/ping` — the same URI as a public GET, but a **state-changing action**.
- `GET /no-such-path` — a URL with no controller at all.
- Actuator endpoints, static files, API docs, endpoints from another servlet, another management port, or an app behind a proxy.

Attackers rarely know every exact endpoint upfront. They probe paths, HTTP methods, prefixes, legacy routes, encoding variants, or secondary paths leaked in OpenAPI specs, JavaScript, logs, or error messages. If policy protects only the handful of remembered URLs, new or old routes easily become unauthorized entry points.

**Lesson goal:** prove with tests that requests outside the allowlist **never reach a business handler** and cause no side effects, while approved endpoints keep working. Unlike document-ownership testing, here you must first verify whether **both the URL and HTTP method** belong to the approved API surface.

## 2. Distinguishing non-existent URLs from unapproved URLs that have handlers

| Request category | Example | What to verify |
|---|---|---|
| **Listed + allowed** | `GET /public/ping` | Works properly without login |
| **Listed + protected** | `GET /api/documents/101` | Only principals with matching permissions can access |
| **Unlisted yet has handler** | `GET /internal/diagnostics` | Handler never runs, even when the caller is logged in or an admin |
| **Same URL, different method** | `POST /public/ping` | Public GET does not imply public POST |
| **Sub-path under similar prefix** | `GET /api/documents/101/export` | Permission to read a document does not automatically permit export |
| **No handler** | `GET /no-such-path` | Distinguish 404 due to missing mapping from Spring Security protection |
| **Not covered by any security chain** | URL outside every `securityMatcher` | Potential security gap, even if every chain has `anyRequest().denyAll()` |

**A 404 response does not prove an API is secure.** It may simply mean no controller exists yet; once a controller is added in a later deploy, that request can immediately become reachable if a broad rule applies. To prove "deny by default" behavior, create **real test endpoints with mappings outside the allowlist**, and verify even authenticated callers cannot reach them.

**A 403 response also does not always prove URL authorization:** `POST/PATCH/DELETE` requests can be rejected by `CsrfFilter` before reaching URL authorization. Negative tests on HTTP methods must supply a valid CSRF token when testing the authorization branch, and test CSRF separately.

## 3. Deny by default rule

In Spring Security Servlet, `authorizeHttpRequests` defines request-level authorization rules. `requestMatchers` are evaluated in declaration order; once a rule matches, that rule decides whether processing continues.

Allowlist-oriented example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/{id}")
        .hasAnyRole("USER", "ADMIN")
    .requestMatchers(HttpMethod.GET, "/admin/report").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

This is an **illustrative configuration snippet** requiring `HttpSecurity`, `HttpMethod` import, and placement inside a `SecurityFilterChain`. Section 5 provides a complete class.

Essential points:

1. **Combine HTTP method + path** whenever GET permissions differ from POST/PATCH/DELETE. Writing `.requestMatchers("/public/ping").permitAll()` alone can open **all methods** on that URI depending on actual routes/handlers.
2. **Place specific rules first**, and the catch-all `.anyRequest().denyAll()` last. Putting `.requestMatchers("/**").permitAll()` first swallows every request and renders later rules dead.
3. `.denyAll()` blocks only requests **that enter the chain containing that rule**. It cannot protect URLs that match no `SecurityFilterChain` at all.
4. Overbroad rules like `"/api/**"` or `"/admin/**"` can accidentally authorize newly added endpoints. Use wildcards only when the **entire** endpoint family shares the same policy, and test sensitive sub-paths.
5. `hasRole("ADMIN")` checks `ROLE_ADMIN`, yet "admin" does not mean access to every endpoint. If an internal route sits outside the approved list, regular admins must be denied too.
6. `denyAll` is an **access decision**; the HTTP status depends on authentication state and the entry point/denied handler. With HTTP Basic in the example: anonymous typically gets `401`; authenticated callers get `403`.

### Why might "anyRequest().authenticated()" not be enough?

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/**").hasRole("USER")
    .anyRequest().authenticated()
);
~~~

This is an **example of unintentional over-permissiveness** if the product only intends to serve a small set of valid routes. Any caller with valid credentials can hit a newly added controller at `/internal/diagnostics`, since the catch-all only requires login. `/api/**` may also cover unexpected export/debug APIs; `hasRole("USER")` neither checks the action nor ownership.

When business policy states "only declared routes may be served," use an explicit allowlist and a deny-all fallback. If the app needs login pages, static assets, error pages, or public health checks, list those **explicitly approved** entries instead of opening `/**`.

## 4. Testing at the right layers: chain selection, authorization, and MVC mapping

~~~mermaid
flowchart TD
    A["HTTP request: method + path + headers"] --> B{"Matching SecurityFilterChain?"}
    B -->|"No"| X["Not protected by that Spring Security chain<br/>must inspect and fix configuration"]
    B -->|"Yes"| C["Authentication / CSRF / filters"]
    C --> D{"authorizeHttpRequests rule?"}
    D -->|"Listed + allow"| E["DispatcherServlet / Controller"]
    D -->|"Listed + deny"| F["401 / 403 depending on case"]
    D -->|"No specific rule matched"| G["anyRequest().denyAll()"]
    G --> F
    E --> H{"Controller mapping?"}
    H -->|"Yes"| I["Handler executes"]
    H -->|"No"| J["404 / 405 / matching MVC response"]
~~~

**Two matchers with different roles:**

- `securityMatcher(...)` scopes **which requests an entire `SecurityFilterChain` applies to**; the first matching filter chain in priority order is selected.
- `requestMatchers(...)` inside `authorizeHttpRequests` defines authorization rules **only for requests that entered that chain**.
- `DispatcherServlet` / Spring MVC picks which controller matches URI + method after security filters let the request pass (in typical configs).

Never cite a 404 when no handler exists as proof that `securityMatcher` covers that URL. Nor should you infer from `/api/foo` being blocked that `/legacy/foo` is protected—another prefix may fall outside the chain.

### Bug example with multiple SecurityFilterChains

~~~java
// INCOMPLETE CONFIG: illustrates a bug; do not use as a complete configuration.
@Bean
@Order(1)
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
    return http.build();
}
~~~

Despite `.anyRequest().denyAll()`, this chain applies **only** to `/api/**`. If no other chain matches `/internal/diagnostics` or `/legacy/export`, Spring Security does not protect those URLs. Once you define your own `SecurityFilterChain` bean, never assume Spring Boot adds another default fallback chain automatically.

The structural fix is registering a final chain **without a restricting `securityMatcher`**:

~~~java
// Illustrative config snippet replacing the incomplete config above.
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
    return http.build();
}
~~~

In a real app, configure authentication/entry points, sessions, CSRF, specific chains, ordering, and intentionally open endpoints thoroughly. If an `@Order(1)` chain uses `securityMatcher("/**")`, the `@Order(2)` chain will **never receive any request**. For this lesson's scope, the complete example uses **one catch-all chain** to focus on allowlist testing.

## 5. Runnable example: an API with "accidentally exposed" endpoints

The demo application has **explicitly allowed** routes:

- `GET /public/ping` — public;
- `GET /api/documents/{id}` — user or admin;
- `GET /admin/report` — admin only.

At the same time, we intentionally **register a controller holding endpoints unlisted in policy**. Although those Java methods truly exist, no principal may invoke them thanks to the denyAll catch-all. An `UnexpectedEndpointProbe` counter proves the handlers **never executed**.

**Environment:** Java 17+, Maven 3.9+, Spring Boot 3.5.0 (Spring Security 6.x). Password `pw` is **for learning environments only**; never expose it on the Internet.

Structure:

~~~text
unexpected-endpoints-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/unexpected/
    │   ├── UnexpectedEndpointsApplication.java
    │   ├── SecurityConfig.java
    │   ├── AllowedController.java
    │   └── UnlistedController.java
    └── test/java/com/example/unexpected/
        └── UnexpectedEndpointSecurityTest.java
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>unexpected-endpoints-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 5.2. UnexpectedEndpointsApplication.java

~~~java
package com.example.unexpected;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UnexpectedEndpointsApplication {
    public static void main(String[] args) {
        SpringApplication.run(UnexpectedEndpointsApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java

~~~java
package com.example.unexpected;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/documents/{id}")
                    .hasAnyRole("USER", "ADMIN")
                .requestMatchers(
                    HttpMethod.GET, "/admin/report").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        // Intentionally keep default CSRF protection.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}pw")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}pw")
                .roles("ADMIN")
                .build());
    }
}
~~~

Read in exact order:

1. `DispatcherType.ERROR` and `FORWARD` are permitted so MVC/the container can render error/forward dispatches without being blocked by catch-all in the demo. This is a **dispatcher type**, distinct from exposing URL `/error` on normal requests; in real apps define which dispatches to permit and test related forwards.
2. `GET /public/ping` is opened for that exact method; `POST /public/ping` **does not** inherit `permitAll`.
3. `GET /api/documents/{id}` is open to `USER` or `ADMIN`, while `GET /api/documents/101/export` does not match the single-segment pattern `{id}`.
4. `GET /admin/report` is for `ADMIN` only; `GET /admin/report/archive` **does not** match the exact route and falls into `denyAll`.
5. Every other request in **this app-wide chain** hits `denyAll`. No `securityMatcher("/api/**")` narrows the chain.
6. `httpBasic` sets up two demo identities; `STATELESS` requires credentials on every request.
7. Default CSRF is not disabled. In `POST` tests, include `with(csrf())` to separate authorization denial from CSRF denial.
8. `{noop}` is a demo password encoder for learning. Production needs real password hashing, secret management, and HTTPS.

### 5.4. AllowedController.java

~~~java
package com.example.unexpected;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AllowedController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/documents/{id}")
    public String document(@PathVariable long id) {
        return "document:" + id;
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }
}
~~~

This controller defines three *allowlisted* endpoints. This is a path-testing demo; `document(...)` stores no real data. In production apps, document GET must also enforce **ownership/tenant/object-level authorization** in services/repositories. A URL match and `ROLE_USER` are not enough to protect each document ID's contents.

### 5.5. UnlistedController.java

~~~java
package com.example.unexpected;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UnlistedController {

    private final UnexpectedEndpointProbe probe;

    public UnlistedController(UnexpectedEndpointProbe probe) {
        this.probe = probe;
    }

    @GetMapping("/internal/diagnostics")
    public String diagnostics() {
        probe.recordCall();
        return "sensitive-debug-output";
    }

    @GetMapping("/legacy/export")
    public String legacyExport() {
        probe.recordCall();
        return "legacy-sensitive-export";
    }

    @GetMapping("/api/documents/101/export")
    public String documentExport() {
        probe.recordCall();
        return "document-101-export";
    }

    @GetMapping("/admin/report/archive")
    public String archivedReport() {
        probe.recordCall();
        return "archived-report";
    }

    @PostMapping("/public/ping")
    public String unexpectedMutation() {
        probe.recordCall();
        return "unexpected-write";
    }
}

// Package-private test probe in the same file; no reset endpoint exposed.
@Component
class UnexpectedEndpointProbe {
    private final AtomicInteger calls = new AtomicInteger();

    void recordCall() {
        calls.incrementAndGet();
    }

    int callCount() {
        return calls.get();
    }

    void reset() {
        calls.set(0);
    }
}
~~~

All mappings in `UnlistedController` **genuinely exist** in Spring MVC. They are "unlisted" because `SecurityConfig` has not approved them, not because `@GetMapping` is missing.

If any request reaches these methods, `probe.recordCall()` increments the counter. Negative tests assert both the status code and `callCount() == 0`. This provides stronger proof than merely probing an unmapped URL and seeing 404.

The counter is for learning only, shared across the Spring context. Tests in the example run sequentially under default JUnit settings; when running in parallel or across processes, use independent fixtures and never rely on a singleton counter to judge another test's requests.

## 6. Negative test matrix: unlisted URLs, different methods, and different principals

The matrix should distinguish **paths with unapproved handlers** from **unmapped URLs**. With section 5's configuration:

| ID | Request | Principal | Expected status | Handler must not run? |
|---|---|---|---|---|
| ALLOW-01 | `GET /public/ping` | Anonymous | 200 | Public handler **does** run |
| ALLOW-02 | `GET /api/documents/101` | Alice / USER | 200 | Document handler **does** run |
| ALLOW-03 | `GET /admin/report` | Admin / ADMIN | 200 | Report handler **does** run |
| DENY-01 | `GET /api/documents/101` | Anonymous | 401 | Document handler does not run |
| DENY-02 | `GET /admin/report` | Alice / USER | 403 | Report handler does not run |
| UNLIST-01 | `GET /internal/diagnostics` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-02 | `GET /legacy/export` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-03 | `GET /api/documents/101/export` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-04 | `GET /admin/report/archive` | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-05 | `POST /public/ping` + valid CSRF | Admin / ADMIN | 403 | Probe = 0 |
| UNLIST-06 | `DELETE /api/documents/101` + valid CSRF | Admin / ADMIN | 403 | No DELETE executed |
| UNLIST-07 | `GET /no-such-path` | Admin / ADMIN | 403 | Unmapped URL; denyAll runs **before** MVC |
| UNLIST-08 | `GET /internal/diagnostics` | Anonymous | 401 | Probe = 0 |

`401` and `403` in the matrix are the **expected behavior of the example's HTTP Basic + denyAll configuration**, not immutable status codes for every Spring Security app. In a form-login app, anonymous may redirect `302`; an app without a catch-all policy might return `404` or accidentally return `200` for a sensitive handler.

Every row needs: actor, method, URL, headers, expected status, expected data, and expected side effects. For multipart uploads, files, webhooks, GraphQL, or WebSockets, also define handshake/upgrade checks and test each access mode.

## 7. MockMvc and JUnit 5: proving denyAll works

Create `src/test/java/com/example/unexpected/UnexpectedEndpointSecurityTest.java`:

~~~java
package com.example.unexpected;

import java.util.stream.Stream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
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
class UnexpectedEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    UnexpectedEndpointProbe probe;

    @BeforeEach
    void resetProbe() {
        probe.reset();
    }

    static Stream<Arguments> unlistedRequests() {
        return Stream.of(
            Arguments.of("UNLIST-01 internal", "GET",
                "/internal/diagnostics"),
            Arguments.of("UNLIST-02 legacy", "GET",
                "/legacy/export"),
            Arguments.of("UNLIST-03 nested export", "GET",
                "/api/documents/101/export"),
            Arguments.of("UNLIST-04 archived report", "GET",
                "/admin/report/archive"),
            Arguments.of("UNLIST-05 method mismatch", "POST",
                "/public/ping"),
            Arguments.of("UNLIST-06 delete method", "DELETE",
                "/api/documents/101"),
            Arguments.of("UNLIST-07 unknown route", "GET",
                "/no-such-path")
        );
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("unlistedRequests")
    void unlistedRequestIsBlockedEvenForAdmin(
            String caseId, String method, String path)
            throws Exception {

        MockHttpServletRequestBuilder request = switch (method) {
            case "GET" -> get(path);
            case "POST" -> post(path).with(csrf());
            case "DELETE" -> delete(path).with(csrf());
            default -> throw new IllegalArgumentException(method);
        };

        mvc.perform(request.with(httpBasic("admin", "pw")))
            .andExpect(status().isForbidden());

        // A 403 status alone is not enough: handler calls must be 0.
        assertThat(probe.callCount()).isZero();
    }

    @Test
    void expectedPublicRouteWorksWithoutAuthentication()
            throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void listedUserRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/documents/101"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/documents/101")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isOk())
            .andExpect(content().string("document:101"));
    }

    @Test
    void listedAdminRouteRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin/report")
                .with(httpBasic("alice", "pw")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/report")
                .with(httpBasic("admin", "pw")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }

    @Test
    void anonymousCannotCallUnlistedHandler() throws Exception {
        mvc.perform(get("/internal/diagnostics"))
            .andExpect(status().isUnauthorized());

        assertThat(probe.callCount()).isZero();
    }

    @Test
    void csrfFailureIsSeparateFromUrlAuthorization()
            throws Exception {
        // Blocked due to missing CSRF token.
        mvc.perform(post("/public/ping")
                .with(httpBasic("admin", "pw")))
            .andExpect(status().isForbidden());

        // Still 403 with valid CSRF: denyAll now blocks the method.
        mvc.perform(post("/public/ping")
                .with(httpBasic("admin", "pw"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        assertThat(probe.callCount()).isZero();
    }
}
~~~

### Why does this test have strong fault-detection power?

- `@SpringBootTest` and `@AutoConfigureMockMvc` set up the **real** Spring Security filter chain in the test app, alongside Spring MVC controllers with real mappings. No TCP port needs to be opened.
- `httpBasic("admin", "pw")` proves **even high-privilege roles** cannot bypass the allowlist; testing only anonymous is not enough.
- `@ParameterizedTest` runs the same verification across multiple paths/methods; each case has a name, status assertion, and `probe.callCount()`.
- `with(csrf())` on POST/DELETE isolates authorization; CSRF is tested separately. Omitting the token could let a CSRF 403 mask a broken `permitAll`.
- `GET /no-such-path` as admin returns 403 in this config because **`denyAll` blocks before controller mapping**. Changing catch-all to `authenticated()` would return 404 for unmapped URLs, and a new real endpoint at that path would immediately become reachable.
- `POST /public/ping` has a real handler and is open publicly for **GET**; the test separates permissions by HTTP method.
- Testing the three allowed routes ensures they keep working after adding default-deny, avoiding overly tight configs that break valid features.
- The probe distinguishes "blocked before controller" from "handler ran and returned an error afterward." Real systems must also inspect databases, events, files, caches, or external calls for routes with side effects.

**Probe limitations:** it counts only the demo handlers in `UnlistedController`; real applications must verify side effects of actual services/domains. The suite does not prove proxies, gateways, Actuator on a separate port, or custom servlets share the same chain. Those layers need integration/E2E tests against real HTTP entry points.

## 8. Running and analyzing results

In the directory containing `pom.xml`:

~~~bash
mvn test
~~~

When tests pass, Maven Surefire typically prints `BUILD SUCCESS` and reports the executed JUnit tests. These are **expected results**, not a report of execution inside this document.

You can start the app to test GET requests from a terminal:

~~~bash
mvn spring-boot:run
~~~

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/101
curl -i -u alice:pw http://localhost:8080/api/documents/101
curl -i -u admin:pw http://localhost:8080/admin/report
curl -i -u admin:pw http://localhost:8080/internal/diagnostics
curl -i -u admin:pw http://localhost:8080/legacy/export
curl -i -u admin:pw http://localhost:8080/no-such-path
~~~

Under the demo setup, the main statuses in order are: `200`, `401`, `200`, `200`, `403`, `403`, `403`. Secondary headers and default error bodies depend on the servlet container/Spring Boot; do not compare full error body strings literally.

On Windows PowerShell, use `curl.exe` to avoid the `curl` alias. Manual POST/DELETE requests are also subject to CSRF; use MockMvc as in section 7 to test authorization independently of CSRF token issuance.

**Do not conclude variant paths produce identical responses across every server:** forms like `//`, `/api/documents/101/`, `%2F`, `%2e%2e`, `;` (matrix parameters), double-encoded URLs, or case variations can be handled differently by proxies, servlet containers, Spring MVC, and `HttpFirewall`. Policies must be tested through the real deployment infrastructure before claiming they are rejected with the same status code.

## 9. Testing scenarios that commonly surface outside the allowlist

### 9.1. Path typos, aliases, trailing slashes, and normalized paths

URLs resembling official routes can be accepted by one routing layer even if another disagrees, such as `/api/documents/101/`, `/api//documents/101`, or `/api/documents%2F101`. Tests must verify whether **responses are blocked or allowed per policy**, never assuming every server parses identically.

When writing custom `RequestMatcher`s, avoid ad-hoc URI string comparisons that ignore context path/servlet path, query strings, or decoding rules; prefer matchers aligned with the running Spring MVC setup. Never implement "loop-decode until no `%` remains" or strip `..` with naive string replacements. Rely on normalization and firewalls provided by the HTTP stack, then test variants at ingress.

Test milestones should capture both the **raw path** sent by the client and the **final Spring MVC route** resolved; when proxies rewrite paths, inspect proxy config to see what actually reaches the app.

### 9.2. HTTP methods outside the policy

The same URI can receive multiple methods:

~~~http
GET /public/ping HTTP/1.1
~~~

~~~http
POST /public/ping HTTP/1.1
Content-Type: application/json

{"action":"change"}
~~~

If `GET` is public while `POST` mutates data, a rule omitting `HttpMethod` is dangerous. Test each sensitive method against real mappings, including `GET`, `POST`, `PUT`, `PATCH`, `DELETE`; `HEAD`, `OPTIONS`, and CORS preflights need their own matching policies. Do not assume `OPTIONS` must always return 403: browsers may need preflights to use valid APIs, and Spring Security/CORS must be configured consistently.

If the app supports HTTP method override via headers/query/filters, test the method **both before and after transformation**. Proxies and gateways can also alter methods. Authorization must enforce rules on the method actually handled by the controller.

### 9.3. Secondary routers, Actuator, docs, static files, and other servlets

Endpoints may exist under `/actuator/**`, `/swagger-ui/**`, `/v3/api-docs/**`, `/h2-console/**`, `/static/**` assets, custom servlets, or a separate management port. Never add them blindly to `permitAll` just to make a UI load.

Some endpoints are not in the main MVC `RequestMappingHandlerMapping` or run under a **different application context/management port**. A MockMvc suite on the main app does not prove those are blocked. Inventory all surfaces, verify real routes, add HTTP tests against management ports/proxies, and disable unneeded endpoints.

For public static assets, Spring Security typically recommends `permitAll` over `web.ignoring`, because bypassing the filter chain can also skip the chain's security headers. `permitAll` still lets relevant filters run.

### 9.4. Multiple chains and priority ordering

In multi-`SecurityFilterChain` architectures, `FilterChainProxy` selects a chain by `@Order`/priority. A URL may hit an unexpected chain, or **no chain at all**. This is a bug class that tests hitting only `/api/**` easily miss.

Verify the rule: **every protected request must match at least one policy-compliant chain**; an unrestricted fallback chain should sit last. If the app intentionally leaves URLs outside Spring Security (e.g., resources served solely by proxy/nginx), document access controls at that layer instead of inferring from an MVC test.

In development, you can temporarily enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Logs reveal filter chains/matchers/authorization during diagnosis. Never log credentials, session cookies, or Bearer tokens in production. Never rely on logs as a substitute for tests.

### 9.5. When mappings change across versions or feature flags

Legacy routes can linger after migrations. Feature flags or profiles can enable internal routes in only one environment. A passing test on the `test` profile does not guarantee the `prod` profile registers no extra controllers.

Cross-check the route inventory under the matching deployment profile and test at least the features/configs that affect mappings or chain selection. Legacy/deprecated paths need explicit decisions: retain with protection, disable, or delete along with their dependencies.

## 10. Scaling tests from a demo to a real system

### Step 1 — Build the allowlist from the API contract

List valid methods/paths and permissions per user group using approved OpenAPI specs, controller mappings, business requirements, and security policies. Every public endpoint needs justification; never assume `/public` in a name makes all methods safe.

Contract example:

~~~yaml
routes:
  - method: GET
    path: /public/ping
    authorization: PUBLIC
  - method: GET
    path: /api/documents/{id}
    authorization: USER_OR_ADMIN
  - method: GET
    path: /admin/report
    authorization: ADMIN
default: DENY
~~~

This YAML is **illustrative policy data**, not a config Spring Security reads automatically. To generate tests from it, write code that reads/compiles the contract and verifies it independently of the implementation.

### Step 2 — Collect the real endpoint inventory

Pull mappings from Spring MVC's `RequestMappingHandlerMapping` in a test context, from protected Actuator mappings endpoints, or from a verified contract/route registry. Never equate the MVC inventory with the entire surface area (static/proxy/management/custom servlets).

To catch **unexpected** mappings, diff the live set (method + path pattern + handler) against the approved list rather than only probing manually chosen URLs. Whenever a new API is added, code review must update both the policy and allowlist tests together.

### Step 3 — Generate meaningful negative cases

Representative categories:

| Category | Cases |
|---|---|
| Internal routes | `/internal/**`, `/debug/**`, `/actuator/**` per actual exposure |
| Legacy routes | Old prefixes/versions, deprecated handlers, redirect/forward aliases |
| Look-alike routes | Child prefixes, nested routes, trailing-slash and casing variants |
| Methods | POST/PATCH/DELETE on GET-only URLs, or method overrides |
| Principals | Anonymous, regular user, admin, cross-tenant user |
| Payloads | Invalid IDs, nested IDs, oversized/wrongly typed path variables |
| Infrastructure | Reverse-proxy rewrites, context paths, management ports, custom servlets |
| Releases | Mappings active only under specific profiles/feature flags |

Do not fire thousands of blind requests at production; design tests in authorized environments with proper fixtures, permissions, and controlled load. For path variants, a firewall `400`, unmapped `404`, or policy `403` can all be safe depending on the case—**provided the sensitive handler never runs or leaks data**.

### Step 4 — Assert both responses and side effects

Every negative test should verify:

- Status matching the contract (and `WWW-Authenticate` for 401 when appropriate).
- Bodies/headers expose no secrets, stack traces, internal paths, or unauthorized object info.
- Business handlers did not run or state stayed invariant: DB row counts, files, messages/events, exports, caches, audit records.
- No redirects/forwards to sensitive endpoints outside policy.
- No chain gaps in production configuration.
- Positive tests confirm approved endpoints still work.

Merely probing unmapped URLs and asserting 404 yields near-zero security coverage: **you need real endpoints that exist yet are intentionally disallowed**, as in the example.

### Step 5 — Wire into CI and review workflows

Run the test matrix whenever adding controllers, editing `SecurityFilterChain`, changing `requestMatchers`, enabling actuator/docs, modifying ingress/routing, or upgrading the Servlet stack. When policy changes, update the approved allowlist and expected tests **first**, then change the implementation. Never rubber-stamp new runtime mappings as valid without review.

Reports should clearly show `test case ID / method / path / actor / expected / actual / handler invoked?` so reviewers can separate security rule bugs from CSRF, mapping, or startup config issues.

## 11. Common pitfalls

1. **Confusing a catch-all rule with a catch-all chain:** `anyRequest().denyAll()` inside an `/api/**` chain does not protect `/legacy/**` if no other chain matches it.
2. **Using `anyRequest().authenticated()` when policy requires an allowlist:** any logged-in user can invoke newly appearing controllers.
3. **Putting `permitAll("/**")` or broad wildcards before sensitive rules:** the first matching matcher can grant unintended access.
4. **Omitting HTTP method constraints:** allowing `GET /public/foo` does not mean `POST /public/foo` should be allowed.
5. **Testing only anonymous:** unlisted handlers may still be exposed to any logged-in user, including cross-tenant admins.
6. **Testing only 404 on non-existent URLs:** reveals nothing about how policy treats a real controller.
7. **Treating a CSRF 403 as proof of method authorization:** supply valid CSRF in authorization tests and test missing CSRF separately.
8. **Checking only HTTP status:** a business handler could trigger side effects before throwing an error; check state/interactions.
9. **Testing only MockMvc while ignoring gateways/management ports:** URLs may be rewritten or served on a separate context; test through real entry points.
10. **Treating UUIDs or obscure URLs as security:** knowing a URL is not authorization; object-level policy must still apply.
11. **Replacing `permitAll` with `web.ignoring` for static/docs:** bypassing the filter chain drops security headers and related defenses.
12. **Mixing up HTTP 401/403/404:** 401 typically means missing valid auth, 403 means permission denied, 404 means unmapped/missing or intentionally hidden resource. Tests should clarify which layer generated the response.
13. **Failing to scope custom servlets/servlet paths:** default request matchers may need explicit config when an app hosts multiple servlets.
14. **Trusting passing tests on a profile different from production:** mappings/security filters can vary by profile, conditional beans, or deployment.

## 12. Exercises and self-check questions

1. When `/api/**` is the sole chain and `anyRequest().denyAll()` is inside it, what happens to a controller at `/internal/diagnostics`? Why?
2. Why is `GET /unknown` returning `404` insufficient proof that the security configuration is safe?
3. In the example, why can admin call `GET /admin/report` yet `GET /admin/report/archive` returns `403`?
4. If `.requestMatchers(HttpMethod.GET, "/public/ping").permitAll()` is changed to `.requestMatchers("/public/ping").permitAll()`, which test exposes the risk of `POST` being permitted?
5. If `POST /public/ping` returns 403 without CSRF, why must you retest with `with(csrf())` before concluding `denyAll` works?
6. Add a new controller `GET /api/documents/101/share`. Write tests ensuring both users and admins are denied until policy approves it.
7. If `GET /api/documents/999` matches a USER-authorized route yet no record exists, which HTTP status makes sense? What should you check to distinguish a data error from a URL policy error?
8. Given two `SecurityFilterChain`s with `@Order(1)` and `@Order(2)`, which chain handles `/legacy/export` if the first matches only `/api/**` and the second has no `securityMatcher`?
9. If an endpoint runs on a separate management port, is `@AutoConfigureMockMvc` on the main app enough to prove it is protected? Where should extra tests run?
10. If a test asserts only 403 yet the probe counter still increments, what do you conclude about security and how do you fix it?

**Completion criteria:** you can build an approved HTTP method + path allowlist, define default behavior for unlisted requests, distinguish `securityMatcher` from `requestMatchers`, write negative tests against **real** yet unauthorized controllers, verify both statuses and side effects, and catch chain gaps in multi-chain apps.

## Official reference documentation

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Multiple HttpSecurity / SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Architecture and FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
