# Testing Unexpected Paths to Detect Protection Gaps

In **Spring Security Servlet**, an application can accurately protect every URL the developer remembered to declare, yet still leave an adjacent URL exposed: a path with an extra segment, a legacy endpoint, a different HTTP method, a route under a context path, or a path entering an unintended `SecurityFilterChain`. In those cases authentication works fine, yet **request matching or authorization coverage** is broken.

**Testing unexpected paths** (negative-path testing) means proactively sending requests outside the permitted list and proving they are blocked at the appropriate security boundary. It is not enough to assert a non-200 status. For instance, HTTP **404** because Spring MVC cannot find a controller does not prove `AuthorizationFilter` rejected the request; HTTP **403** from `CsrfFilter` does not prove role rules ran; HTTP **401** for anonymous users may be the authentication entry point of a deny rule. You must know **which layer** produced the outcome.

This lesson targets **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/MVC**. It covers two matcher layers, deny-by-default policies, path and method groups to test, a two-SecurityFilterChain config example, MockMvc tests with real identities/CSRF, real HTTP server tests, URL normalization checks, proxy/context/servlet paths, route manifests, and a regression-prevention checklist. Specific matchers (`MvcRequestMatcher`, `AntPathRequestMatcher`, `PathPatternRequestMatcher`) have version/configuration-dependent semantics, so you cannot assume every raw URL is handled identically.

## 1. What Is a Protection Gap?

A protection gap occurs when at least one request can reach functionality that ought to require permission checks **without passing through the intended authentication/authorization conditions**.

~~~text
Original intent:
  GET /api/reports/{id} -> requires REPORT_READ

Additional request paths to test:
  GET    /api/reports/10
  GET    /api/reports/10/export
  GET    /api/reports/10.json
  GET    /api/reports/10/
  POST   /api/reports/10
  GET    /api/report-old/10
  GET    /admin/reports
  GET    /api
  GET    /public/../api/reports/10
~~~

URLs with dots, encoded separators, or dot segments are solely **inputs for designing defensive tests**: proxies, servlet containers, and `StrictHttpFirewall` may normalize or reject requests **before** reaching any matcher. Never treat them as equivalent forms across every system.

| Gap Type | Example | Risk |
| --- | --- | --- |
| Overly broad public matcher | `/api/**` with `permitAll` placed before protected rules | Accidentally exposes sensitive endpoints |
| Overly narrow protected matcher | Checks only one exact URL, misses export/alias | Secondary endpoint lacks rules |
| Missing catch-all chain | Only `securityMatcher("/api/**")` declared | Controllers outside `/api` skip Spring Security |
| Unconstrained method | Protects GET, forgets POST/DELETE on same URL | Unintended write access |
| Dispatcher/servlet path mismatch | App mounted under `/portal` | Test rules differ from production |
| Divergent path normalization | Encoded slash, double slash, semicolon | Gateway and app interpret path differently |
| Legacy route still alive | `/v1/report-export` | Old alias bypasses new rule |
| Multiple filter chains | API chain and web chain ordered differently | Unexpected chain selected |
| New controller mappings | Auto-config routes, actuator if enabled | New routes unclassified |
| Missing object-level policy | User has READ permission but does not own record | Not a path bug, yet still leaks data |

**Success criteria:** valid routes work with the right permissions; out-of-contract routes/identities/methods are blocked; no alternative path reaches the same business operation while bypassing permission checks.

## 2. Two Matching Layers to Test Separately

When a request enters Spring Security Servlet, `FilterChainProxy` locates the **first matching SecurityFilterChain**. Inside that chain, filters execute and `AuthorizationFilter` enforces policies from `authorizeHttpRequests(...)`.

~~~text
HTTP request
     |
     v
FilterChainProxy
     |
     +-- Chain #1: securityMatcher("/api/**")
     |      |
     |      +-- GET /api/records/{id} -> RECORD_READ
     |      +-- POST /api/records/{id} -> RECORD_WRITE
     |      +-- anyRequest().denyAll()
     |
     +-- Chain #2: catch-all (no narrow securityMatcher)
            |
            +-- GET /public/ping -> permitAll()
            +-- anyRequest().denyAll()
~~~

If a request matches Chain #1, it **does not continue to Chain #2** for a second decision. If it matches no chain at all, the request may skip Spring Security processing entirely, even when Spring MVC has a real controller.

### securityMatcher and requestMatchers Are Not Synonymous

| API | What It Matches | Consequence on No Match |
| --- | --- | --- |
| `http.securityMatcher(...)` | Entire filter chain | Tries next chain; may match no chain |
| `authorizeHttpRequests(...requestMatchers(...))` | Authorization rule inside the selected chain | Tries next rule |
| `anyRequest().denyAll()` | All remaining requests **inside that chain** | Does not protect paths outside the chain |
| `@GetMapping/@PostMapping` | Spring MVC controller mapping | Does not enforce security policy itself |

Common mistake:

~~~java
// API chain only: mistakenly assuming denyAll covers the entire app.
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().denyAll());
    return http.build();
}
~~~

A `GET /admin/export` controller outside `/api/**` may go unprotected by Spring Security if no other chain exists. You need a **fallback chain** or an intentional definition of excluded scopes, followed by tests against real routes to verify.

### Rule Ordering Can Cause Bypasses

~~~java
// WRONG: broad matcher is evaluated first.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/private/**").hasRole("ADMIN")
    .anyRequest().denyAll());
~~~

Request `/api/private/export` can pass through the broad `permitAll` rule before ever reaching the admin rule. Place specific/protected rules first, keep public allowlists strictly to genuinely public URLs, and finish with a deny fallback.

Never assume a rule written in configuration definitely executes; test URLs lying in the **intersection between patterns**.

## 3. Test Matrices Must Include Both Positive and Negative Cases

A test suite consisting solely of 403/401 assertions is misleading: a deny-all config for every URL makes many "access denied" tests green while rendering the app useless and proving nothing about specific rules working.

Include three tiers:

1. **Positive:** valid URL, valid method, and authorized user succeed.
2. **Same-URL negative:** anonymous or under-privileged users are denied.
3. **Out-of-contract negative:** sub-paths, disallowed methods, out-of-chain namespaces, and lookalike URLs are denied.

Example for the app in section 7:

| Request | Credential | Expected | Meaning |
| --- | --- | --- | --- |
| `GET /public/ping` | anonymous | 200 | Public route actually works |
| `GET /api/records/7` | reader / `RECORD_READ` | 200 | Protected route for authorized user |
| `GET /api/records/7` | anonymous | 401 with Basic entry point | Missing authentication |
| `GET /api/records/7` | writer / `RECORD_WRITE` | 403 | WRITE does not substitute for READ |
| `POST /api/records/7` | writer + valid CSRF | 200 | WRITE permission and CSRF satisfied |
| `POST /api/records/7` | reader + valid CSRF | 403 | WRITE permission enforced |
| `POST /api/records/7` | writer missing CSRF | 403 | `CsrfFilter` blocks, distinct from authorization |
| `GET /api/records/7/export` | reader | 403 | Extra segment not allowed |
| `GET /api/records/7.json` | reader | 403 | Suffix not allowed |
| `GET /api/records/7/` | reader | 403 in demo | Trailing slash not auto-opened |
| `GET /api/unknown` | reader | 403 | API fallback deny |
| `GET /api` | reader | 403 | Fallback chain protects exact prefix |
| `GET /admin/diagnostics` | reader | 403 | Non-API routes not left uncovered |
| `GET /public/secret` | reader | 403 | Public allows only ping |

Statuses reflect expectations **for the demo configuration**, not an invariant rule across all Spring Security apps. With form login, an anonymous request may receive a 302 redirect to login. A custom `AccessDeniedHandler` might intentionally return JSON or 404 instead of 403, so verify the actual contract.

### Why Use an Authenticated Identity for Unexpected URLs?

When an anonymous request is denied by authorization, `ExceptionTranslationFilter` may invoke the authentication entry point, returning 401/302. Testing out-of-allowlist paths with an authenticated `reader` yields 403, distinguishing policy denial more clearly from simply not being logged in. Still, 403 can also come from another filter, so configure tests cleanly and keep positive controls.

## 4. 404 Is Not Proof of Security

Consider the request:

~~~http
GET /api/internal/ghost
Authorization: Basic <valid-credentials>
~~~

If 404 is returned, there are two typical possibilities:

- Spring Security let the request through, and Spring MVC found no controller.
- A component intentionally returned 404 after applying some policy.

You cannot see 404 alone and conclude `AuthorizationFilter` denied it. Similarly, 405 Method Not Allowed can come from MVC rejecting the method after passing security.

### How to Prove Security Enforcement

- Run requests against **the same URL that has a real controller** with both an authorized user and an unauthorized user. For example, reader GET record 7 returns 200, while writer GET on the same URL returns 403.
- Test out-of-allowlist URLs with an **authenticated user**; in a deny-by-default design like the demo, expect 403 rather than 404.
- Verify chain matching: API URLs enter the API chain, external routes enter the catch-all chain, and nothing escapes Spring Security altogether.
- For stronger proof, use a test-only controller or spy/service probe to confirm denied requests fail **before any controller executes**.
- Add real HTTP server/proxy integration tests for URLs subject to rewriting or normalization.

**Never ship a vulnerable probe endpoint to production just for security testing.** Sensitive probe routes belong strictly in test profiles/contexts; in production, audit route registries and policies properly.

## 5. List of Path Variants to Test

For canonical endpoint `GET /api/records/7`, construct meaningful groups:

| Group | Example | Watch Out For |
| --- | --- | --- |
| Extra trailing slash | `/api/records/7/` | Matcher/router behavior can vary by version |
| Suffix/extension | `/api/records/7.json` | Can be affected by route aliases or suffix matching |
| Extra subpath | `/api/records/7/export` | `*` vs. `**` pattern differences |
| Missing ID | `/api/records` | Does not match `/{id}` template |
| Missing slash after prefix | `/api` | Do not assume it matches `/api/**` |
| Lookalike prefix | `/api-records/7` | Is it covered by a fallback? |
| Uppercase | `/API/records/7` | Case sensitivity at the routing layer |
| Double slash | `/api//records/7` | Container/proxy/firewall may reject or normalize |
| Dot segments | `/api/public/../records/7` | Each HTTP layer may interpret differently |
| Percent encoding | `/api/records%2F7`, `%2e%2e` | Server may reject or decode |
| Matrix parameters | `/api/records/7;mode=view` | Semicolon may be rejected by `StrictHttpFirewall` |
| Unicode | URLs with Unicode or UTF-8 encoded chars | Normalization, charset, matcher semantics |
| Query string | `/api/records/7?export=true` | Path matchers ignore queries; handlers may act differently |
| Fragment | `#section` | Fragments are not sent by browsers in HTTP requests |

Do not treat every variant as an accepted attack vector: some requests should immediately yield 400 from the firewall/container. During testing, identify the **blocking layer** and check whether gateways/proxies alter request shapes before reaching the container.

### Important: Matching a URL and Authorizing an Action Are Different

A GET URL with query `?export=true` usually matches the same path as GET without query, yet the controller might trigger an export based on that query. Thus if exporting requires separate permission, enforce business authorization in the service or split routes/methods with explicit policies; never expect path matchers to distinguish all business-input variants.

### Routes Outside MVC

Other paths may also need testing:

- Static file resources and uploads/downloads.
- Separately mapped servlets bypassing the main `DispatcherServlet`.
- WebSocket handshakes, SSE, GraphQL endpoints.
- Error pages / forward dispatches.
- Actuator/metrics/debug endpoints if enabled.
- Legacy API versions, aliases, redirect/forward targets.
- Files served via CDN/web servers outside Spring Security's direct control.

If a resource is served **before reaching the Servlet app**, testing Spring Security alone is insufficient; verify access controls at the web server, CDN, object storage, or serving architecture.

## 6. HTTP Methods Do Not Automatically Inherit Permissions

A rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/records/{id}")
    .hasAuthority("RECORD_READ")
~~~

does not grant access to `POST /api/records/{id}` or `DELETE /api/records/{id}`. Another mistake is declaring a matcher without an HTTP method constraint when only GET was intended.

Methods worth evaluating per API:

~~~text
GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE, TRACE
~~~

- GET is typically read-only; it should not cause state-changing side effects.
- HEAD has GET-related semantics in web frameworks, yet path/method matchers may differ; test explicitly.
- OPTIONS may be handled by CORS preflight logic, needing dedicated frontend-appropriate policies.
- POST/PUT/PATCH/DELETE may be rejected by the CSRF filter before authorization when cookies/sessions are used.
- TRACE should be evaluated/blocked at the container/proxy per policy; do not assume MockMvc reflects raw HTTP server behavior.

### Testing CSRF and Authorization Independently

To prove a user lacking WRITE is denied, send the request with a **valid CSRF token** so `CsrfFilter` does not block before `AuthorizationFilter` runs. Write separate cases:

~~~text
writer POST /api/records/7 + csrf -> 200 (has WRITE)
reader POST /api/records/7 + csrf -> 403 (lacks WRITE)
writer POST /api/records/7 no csrf -> 403 (CSRF)
~~~

Never deduce root causes from HTTP 403 alone; positive controls and clean test setups let you isolate each layer.

## 7. Spring Boot Example: API Chain and Catch-All Chain

The demo app uses:

- `/api/**` for the API chain. GET record requires `RECORD_READ`, POST record requires `RECORD_WRITE`, other API routes are denied.
- Fallback chain without a narrow `securityMatcher`: only `GET /public/ping` is allowed without login; all other paths are denied.
- HTTP Basic authentication for simple testing; **production needs HTTPS, a real identity model, and proper abuse controls**.
- `PasswordEncoder` with BCrypt for demo credentials.
- CSRF stays enabled for POST; tests use `with(csrf())`.
- Do not substitute controller unit tests for filter tests; both chains must actually run.

### 7.1. Maven Dependencies

In a Spring Boot 3.x project with compatible parent/BOM/plugins:

~~~xml
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
~~~

Do not mix Spring Security versions outside the BOM. Framework code requires the Boot/Security classpath; only the standalone Java 17 program in section 11 runs on a bare JDK.

### 7.2. Main Class

Create `src/main/java/com/example/pathguard/PathGuardApplication.java`:

~~~java
package com.example.pathguard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathGuardApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathGuardApplication.class, args);
    }
}
~~~

### 7.3. Two SecurityFilterChains With @Order

Create `src/main/java/com/example/pathguard/SecurityConfig.java`:

~~~java
package com.example.pathguard;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-demo-only"))
                .authorities("RECORD_READ")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("writer-demo-only"))
                .authorities("RECORD_WRITE")
                .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/records/{id}")
                    .hasAuthority("RECORD_READ")
                .requestMatchers(
                    HttpMethod.POST, "/api/records/{id}")
                    .hasAuthority("RECORD_WRITE")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Keep CSRF enabled; POST tests must provide csrf().
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        // Do not set a narrow securityMatcher on the catch-all chain.
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/public/ping")
                    .permitAll()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Point-by-point explanation:

1. `@Order(1)` ensures the API chain is evaluated before the catch-all chain.
2. `securityMatcher("/api/**")` limits **chain scope**.
3. Two `requestMatchers(HttpMethod, pattern)` rules separate GET and POST. When a sensitive route gains a new method, it is not implicitly allowed.
4. API `anyRequest().denyAll()` catches out-of-contract API paths.
5. The fallback chain has no narrow `securityMatcher`, protecting paths outside the API namespace, including `/api` if the implementation does not match `/api/**`.
6. Fallback `/public/ping` is an **exact allowlist entry**; never use a broad `/public/**.permitAll()` just because one endpoint needs to be public.
7. Both chains use HTTP Basic; with other auth systems, verify the corresponding authentication/authorization filters for each chain.
8. `csrf.disable()` is not called; this highlights the difference between CSRF denial and role denial.

**Version caveat:** in Spring Security 6.x, DSL matchers may pick `MvcRequestMatcher` or another matcher type depending on classpath/version. On newer versions, `PathPatternRequestMatcher` creation and servlet-path handling may differ. Tests are written against the version pinned in the project; do not guess semantics for encoded paths.

### 7.4. Controller

Create `src/main/java/com/example/pathguard/RecordController.java`:

~~~java
package com.example.pathguard;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RecordController {

    @GetMapping("/api/records/{id}")
    public Map<String, Object> read(@PathVariable long id) {
        // Fake data for demo. Real app needs object-level security.
        return Map.of("id", id, "status", "read");
    }

    @PostMapping("/api/records/{id}")
    public Map<String, Object> write(@PathVariable long id) {
        // Demo does not modify a database.
        return Map.of("id", id, "status", "updated");
    }
}
~~~

Create `src/main/java/com/example/pathguard/PublicController.java`:

~~~java
package com.example.pathguard;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

**Security point:** controllers do not need to know about the deny-all fallback for undeclared URLs; blocking happens in the filter chain. In production, `RECORD_READ` across the whole record group is still not enough when records belong to owners/tenants: service-level/object-level authorization is required. That sits outside path matching, yet still must be evaluated.

### 7.5. Running Locally and Trying Requests

~~~bash
./mvnw spring-boot:run
~~~

Locally, let `curl` prompt for the password instead of putting passwords in shell history:

~~~bash
curl -i -u reader http://localhost:8080/api/records/7
curl -i -u reader http://localhost:8080/api/records/7/export
curl -i -u reader http://localhost:8080/admin/diagnostics
curl -i http://localhost:8080/public/ping
~~~

Expected results when entering the right demo password:

~~~text
reader GET /api/records/7         -> 200
reader GET /api/records/7/export  -> 403
reader GET /admin/diagnostics     -> 403
anonymous GET /public/ping        -> 200
~~~

Never use HTTP Basic over real networks without TLS, and never put production credentials into documentation or logs.

## 8. Integration Tests With MockMvc

Create `src/test/java/com/example/pathguard/PathCoverageIntegrationTest.java`. The suite deliberately includes positive, missing-permission, anonymous, unknown-path, and method cases. It runs through the application context's Spring Security filters.

~~~java
package com.example.pathguard;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathCoverageIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void publicRouteWorks() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk());
    }

    @Test
    void readerCanGetAllowedRecord() throws Exception {
        mvc.perform(get("/api/records/7")
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7));
    }

    @Test
    void anonymousMustAuthenticate() throws Exception {
        mvc.perform(get("/api/records/7"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void writerCannotReadWithoutReadAuthority() throws Exception {
        mvc.perform(get("/api/records/7")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanWriteWithCsrf() throws Exception {
        mvc.perform(post("/api/records/7")
                .with(httpBasic("writer", "writer-demo-only"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("updated"));
    }

    @Test
    void readerCannotWriteEvenWhenCsrfIsValid() throws Exception {
        mvc.perform(post("/api/records/7")
                .with(httpBasic("reader", "reader-demo-only"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingCsrfIsASeparateFailure() throws Exception {
        mvc.perform(post("/api/records/7")
                .with(httpBasic("writer", "writer-demo-only")))
            .andExpect(status().isForbidden());
    }

    @ParameterizedTest(name = "unexpected path {0} is denied")
    @ValueSource(strings = {
        "/api/records/7/export",
        "/api/records/7.json",
        "/api/records/7/",
        "/api/records",
        "/api/unknown",
        "/api",
        "/admin/diagnostics",
        "/public/secret"
    })
    void unexpectedPathIsDenied(String path) throws Exception {
        mvc.perform(get(path)
                .with(httpBasic("reader", "reader-demo-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

An authenticated unexpected request in this sample receives 403 thanks to the deny-all rule in the selected chain. Without the catch-all chain, `/admin/diagnostics` or `/api` would fall through to MVC and return 404, failing the test — fulfilling the goal of exposing coverage gaps.

### 8.1. Why Test POST With Valid csrf()?

A POST without a token can be rejected by `CsrfFilter` with 403 before reaching `AuthorizationFilter`. To prove `RECORD_WRITE` works, the test must send a valid CSRF token. The two tests `reader + csrf` and `writer + csrf` provide evidence of permission checks; `writer without csrf` tests a separate protective layer.

If a production API uses stateless Bearer tokens rather than browser cookies, CSRF policy may be evaluated differently; never disable CSRF just because the body is JSON.

### 8.2. Does a 403 Test Guarantee the API Chain Ran?

Not necessarily. Both the API chain and the fallback chain can deny; a 403 response does not state which chain acted. If your goal is confirming **chain assignment**, add integration assertions with policy instrumentation/test managers or inspect filter chains in a test profile. Combining positive controls and fallback denials still verifies essential properties.

### 8.3. Do Not Use standaloneSetup for Security Tests

`MockMvcBuilders.standaloneSetup(controller)` does not attach `SecurityFilterChain` by default; a controller can return 200 even though production blocks it. Use `@SpringBootTest + @AutoConfigureMockMvc` or register the `springSecurity` filter in test setup. A `@WithMockUser` test is useful for role policies, yet does not prove the HTTP Basic provider/password encoder ran. Using credentials in requests covers filter authentication too.

### 8.4. What If the Trailing-Slash Test Fails?

Inspect the Spring Security matcher, MVC handler mapping, and versions rather than immediately changing the assertion to status 404. The goal of the example is to **block every out-of-allowlist path before MVC**. However, when a matcher has different semantics, a trailing-slash path might be treated as the same valid route; product policy must clearly define which forms are allowed. Classify first, then align matchers and negative tests to the contract.

## 9. Real HTTP Servers/Proxies Differ From MockMvc

A real request traverses:

~~~text
Browser / HTTP client
       |
       v
CDN, reverse proxy, gateway
       | (rewrite/normalize/path decode may happen)
       v
Servlet container (HTTP parser, servlet path)
       |
       v
StrictHttpFirewall / FilterChainProxy
       |
       v
SecurityFilterChain + AuthorizationFilter
       |
       v
Spring MVC controller
~~~

MockMvc simulates requests/filters/dispatcher within the test context; it does **not** guarantee identical behavior to Tomcat/Jetty/Undertow HTTP parsers or production proxies. For double slashes, encoded separators, dot segments, semicolons, Unicode URLs, context paths, forwarded headers, and raw request-targets, test on an **embedded server** and ideally through the same proxy/gateway type used in production.

### Basic HTTP Integration Test Example

Spring Boot 3.x provides `RestClient` and `@LocalServerPort`:

~~~java
package com.example.pathguard;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpPathTest {

    @LocalServerPort int port;

    @Test
    void publicPathWorksThroughRealHttpServer() {
        RestClient client = RestClient.create(
            "http://localhost:" + port);
        String body = client.get().uri("/public/ping")
            .retrieve().body(String.class);

        assertEquals("pong", body);
    }
}
~~~

This is a real HTTP server test for **one valid URL**, not a raw-URL fuzz suite. `RestClient` was introduced in Spring Framework 6.1+; on Spring Boot 3.0/3.1 you may need `WebClient`/`TestRestTemplate` or another HTTP client depending on version. For encoded URLs, an HTTP client may re-encode before sending; know the exact bytes/request-target sent over the wire.

### What Must Production-Like Tests Check?

- Was the request rejected with 400 by the container or blocked by the firewall?
- Does the path after the reverse proxy match what path matchers see?
- Were HTTP methods or servlet mappings transformed?
- Does a chain protect routes outside `/api`?
- Can gateway URL aliases reach controllers?
- Do forwarded headers come only from trusted proxies, or can clients send them directly?
- Do cookies/sessions/context paths affect entry points and auth?
- Does logging safely record both raw request targets and normalized paths without leaking credentials?

A 400 from the firewall/container may be a safe outcome, yet **is not proof that AuthorizationManager denied it**. Record which layer blocked it so version upgrades do not mask behavioral shifts.

## 10. Route Inventory and Testing as the Product Grows

A large app must not rely on memory to list every sensitive URL. Maintain a reviewed **route/policy manifest**:

| Route Family | Method | Policy |
| --- | --- | --- |
| `/public/ping` | GET | Public |
| `/api/records/{id}` | GET | `RECORD_READ` |
| `/api/records/{id}` | POST | `RECORD_WRITE` + appropriate CSRF |
| `/api/records/{id}/export` | GET | Deny until dedicated policy exists |
| `/admin/**` | All methods | Deny in demo |
| Unknown routes | All methods | Deny |

Whenever a new endpoint is added:

1. Extract the actually registered mappings from MVC/actuator mappings (if enabled and properly secured), including routes from auto-config or other modules.
2. Compare against reviewed route entries/families.
3. If a new sensitive route lacks a policy, require review or fail CI.
4. Add anonymous, authorized, and unauthorized tests.
5. Add negative variants of that route: subpaths, extensions, other methods, and lookalike namespaces.
6. Test proxy/context paths if the route sits behind rewrites.
7. Retain regression cases from previously discovered bugs.

Note that not every controller mapping needs its own separate `requestMatchers` line: one pattern rule can cover a logical group of routes. What must be verified is **that the new route is properly classified and the rule actually enforces it**.

### Drift-Check Pseudocode

~~~text
registered = all MVC routes and methods in test context
reviewed = declared security policy manifest

for each route in registered:
    if not covered by reviewed policy:
        fail("UNCLASSIFIED_ROUTE")
    else:
        generate allowed and denied scenarios

for each known risky alternate path:
    execute HTTP test and verify the correct blocking layer
~~~

This is pseudocode, not standalone Java. Matchers accepting path variables and complex regexes have huge path spaces; automated test generation helps, yet **cannot prove infinitely many URLs are all secure**.

## 11. Standalone Java 17: Catch-All and Unexpected-Path Model

The following program uses **plain JDK 17** to model policy classification. It does not use Spring Security, does not handle path normalization/URL encoding, does not verify passwords, and does not simulate HTTP 401/403 itself. Goal: show why both inside-API and outside-API scopes need deny fallbacks.

Save `UnexpectedPathPolicyDemo.java`:

~~~java
public class UnexpectedPathPolicyDemo {

    static String decide(String method, String path,
                         boolean authenticated,
                         String authority) {

        if ("GET".equals(method) &&
                "/public/ping".equals(path)) {
            return "ALLOW_PUBLIC";
        }

        if (path.startsWith("/api/")) {
            if (!authenticated) {
                return "NEED_AUTHENTICATION";
            }

            if ("GET".equals(method) &&
                    "/api/records/7".equals(path) &&
                    "RECORD_READ".equals(authority)) {
                return "ALLOW_READ";
            }

            if ("POST".equals(method) &&
                    "/api/records/7".equals(path) &&
                    "RECORD_WRITE".equals(authority)) {
                return "ALLOW_WRITE";
            }

            return "DENY_API_FALLBACK";
        }

        return "DENY_GLOBAL_FALLBACK";
    }

    public static void main(String[] args) {
        System.out.println(decide("GET", "/public/ping",
            false, ""));
        System.out.println(decide("GET", "/api/records/7",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/api/records/7/export",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/admin/diagnostics",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/api",
            true, "RECORD_READ"));
        System.out.println(decide("POST", "/api/records/7",
            true, "RECORD_READ"));
        System.out.println(decide("GET", "/api/records/7",
            false, ""));
    }
}
~~~

Run on JDK 17+:

~~~bash
javac UnexpectedPathPolicyDemo.java
java UnexpectedPathPolicyDemo
~~~

Exact stdout:

~~~text
ALLOW_PUBLIC
ALLOW_READ
DENY_API_FALLBACK
DENY_GLOBAL_FALLBACK
DENY_GLOBAL_FALLBACK
DENY_API_FALLBACK
NEED_AUTHENTICATION
~~~

Meaning:

- A disallowed sub-path under the API gets `DENY_API_FALLBACK`.
- Admin URLs outside `/api` are rejected by the global fallback.
- Exact prefix `/api` falls into the global fallback in **this simple model**. Real Spring matchers may match differently, yet must still deny if policy does not allow it.
- POST requires `RECORD_WRITE`; `READ` permission is insufficient.
- Anonymous callers cannot access protected endpoints.

Do not copy `path.startsWith("/api/")` as a production HTTP matcher because Spring MVC, Servlet requests, and HTTP normalization are far more complex than plain Java strings.

## 12. Common Pitfalls That Invalidate Tests

### 12.1. Testing Only URLs Listed in Config

If `GET /api/records/7` passes, you have not tested `/api/records/7/export` or `/admin`. Include at least one group of **lookalike and out-of-namespace paths** likely to emerge as routes are added.

### 12.2. Assuming denyAll in the API Chain Covers the Whole App

`anyRequest().denyAll()` in a chain applies only to requests accepted by that chain. You need a catch-all or explicit full-coverage chains, plus tests outside the API.

### 12.3. Making an Entire Namespace Public to Fix One Test

Adding `requestMatchers("/api/**").permitAll()` makes the legitimate route work while potentially exposing hundreds of other endpoints. Declare only exact public routes; secure everything else with roles/authorities/deny.

### 12.4. Using 404 to Prove a Rule Blocked Access

404 can mean MVC lacked a handler after security allowed the request through. Positive + negative tests on **the same real endpoint**, authenticated unknown-path tests, and chain-level instrumentation provide stronger proof.

### 12.5. Ignoring HTTP Methods

If policy allows only GET, never leave matchers unconstrained by method so POST/DELETE are allowed too. Test other methods with valid identities and CSRF where needed.

### 12.6. Confusing CSRF 403 With Missing Authority 403

A POST missing CSRF is rejected earlier; it proves nothing about authorization rules. Test roles with `with(csrf())` and test CSRF separately.

### 12.7. Using Standalone MockMvc

Standalone controller setups omit the full `SecurityFilterChain` unless explicitly attached. They test controllers well, not route security. Use context-backed MockMvc with Spring Security or full HTTP integration tests.

### 12.8. Relying Solely on MockMvc for Encoded Paths

`MockHttpServletRequest` does not simulate all container, proxy, firewall, and decoding nuances. Test raw paths on a real server/proxy. Never assume a firewall 400 is an authorization 403.

### 12.9. Forgetting Multi-Chain Ordering

A catch-all chain placed before an API chain can swallow all API requests, altering effective policy. Use explicit `@Order` and test API URLs with both authorized and unauthorized users.

### 12.10. Forgetting Security on Error/Forward Dispatches

Forwards to sensitive routes or `ERROR` handlers can experience different rules/dispatch behavior depending on Servlet and Spring Security versions. Inspect dispatcher mappings rather than adding a blanket `permitAll` for all forwards just because an error page returned 403.

### 12.11. Testing Only With a Superadmin

A user holding many authorities hides distinctions among READ, WRITE, and tenants. Use least-privilege identities and cross-tenant users where required.

### 12.12. Ignoring Non-MVC Paths

Static files, CDNs, file handlers, or separate Servlets may not traverse the same security chain. Test at the exact layer receiving those requests, not only Spring MVC mappings.

### 12.13. Equating Path Authorization With Object Authorization

Allowing `GET /api/records/7` because of `RECORD_READ` does not prove the user may view record 7. When records belong to different tenants, enforce object-level checks in services/AuthorizationManagers using trusted data. Negative path tests and negative object tests complement each other.

### 12.14. Skipping Post-Upgrade Regression Checks

Spring Security, Spring Framework, servlet containers, and reverse proxies can change path matching/normalization behavior. Keep negative suites in CI and run production-like tests on version upgrades.

## 13. Verification Workflow in Real Projects

1. Inventory all URLs, methods, servlets, and routes actually served by your infrastructure.
2. Document public, authenticated, role, owner-tenant, and deny policies for each group.
3. Cross-check all `SecurityFilterChain`s and `@Order` values against real URLs.
4. Keep public allowlists narrow, protect routes per method, and use deny-all fallbacks.
5. Write a positive test for every critical protected route.
6. Test anonymous and under-privileged identities on the same route.
7. Test other methods while ensuring CSRF does not mask authorization conditions.
8. Test boundary paths: prefixes, suffixes, trailing slashes, child segments, exact namespaces, legacy aliases.
9. Test raw HTTP URLs and reverse proxy rewrites in a production-like environment.
10. Identify which layer returned 400/401/403/404/405; never use generic error statuses as proof.
11. Establish a policy review gate for new routes and keep regression tests for past bugs.
12. Check non-HTTP service callers and object-level authorization too.
13. Never log credentials/tokens/session IDs in test output or debug traces.
14. Only permit newly classified routes; never widen wildcards just to "make tests green".

### Quick Review Checklist

- [ ] A properly scoped fallback chain exists, or intentionally unprotected URLs are explicitly defined.
- [ ] Every sensitive chain has a fallback rule and tests.
- [ ] Public allowlists cannot match ahead of protected rules via overly broad patterns.
- [ ] HTTP methods are explicitly distinguished.
- [ ] At least one allow test and one deny test exist for the same real endpoint.
- [ ] Anonymous callers and authenticated users lacking authorities are both tested.
- [ ] Unknown URLs are tested both inside and outside the API namespace.
- [ ] Exact `/api` prefix, route suffixes, and child segments are tested.
- [ ] POST is tested with valid CSRF to verify roles; CSRF is tested separately.
- [ ] Raw encoded paths are tested through real servers/proxies when within the threat model.
- [ ] Context paths, servlet paths, and proxy forwarded headers are tested.
- [ ] Route inventory is reviewed whenever new controllers/modules are added.
- [ ] Object-level and service-level policies are not overlooked.

## 14. Questions and Exercises

**Ex 1.** Only an API chain `securityMatcher("/api/**")` with `anyRequest().denyAll()` exists. A `GET /admin/export` controller is active. Is it guaranteed to be protected by Spring Security?

**Answer:** No. If no other chain matches `/admin/export`, Spring Security may not process the request. Add a fallback chain or an admin chain and test paths outside the API.

**Ex 2.** `GET /api/unknown` returns 404. Can you conclude deny-all ran?

**Answer:** No. Spring Security may have allowed it through and MVC returned 404 due to no controller. Test a real route with valid/invalid permissions and/or confirm the chain/rule rejects before MVC.

**Ex 3.** `GET /api/records/7`: reader gets 200, writer gets 403. What does this prove?

**Answer:** The real route has a rule requiring READ and distinguishes identities. You still must test lookalike URLs and other methods to check coverage.

**Ex 4.** Reader `POST /api/records/7` without CSRF returns 403. Does that prove `RECORD_WRITE` is missing?

**Answer:** Not yet. `CsrfFilter` may have blocked first. Send valid CSRF and verify reader is denied while writer is allowed.

**Ex 5.** Placing `/api/**.permitAll()` before protected rules. What is the problem?

**Answer:** The broad public matcher matches first, preventing protected rules from running. Place exact public routes and appropriate protected rules ahead of the deny fallback.

**Ex 6.** Does a valid `GET /api/records/7` mean POST on the same URL is also allowed?

**Answer:** No. HTTP method is a separate authorization dimension; dedicated WRITE rules and proper CSRF policies are required.

**Ex 7.** MockMvc rejects an encoded path, yet the production server handles it differently. Why?

**Answer:** Containers, proxies, firewalls, servlet mappings, and test request builders normalize and encode differently. Run integration tests on the real stack.

**Ex 8.** Why test `/api` when the chain specifies `/api/**`?

**Answer:** Exact namespace prefix semantics can vary by matcher. A catch-all ensures that if it misses the API chain, a deny rule still applies. Never guess equivalence.

**Ex 9.** A new route `/api/records/7/export` is added after CI runs. How do you prevent forgetting its policy?

**Answer:** Diff the mapping inventory against the policy manifest, require reviews for new routes, add positive/negative tests, and include an outside-allowlist case for export.

**Ex 10.** A user has `RECORD_READ` and can view another tenant's record. Is this purely a request-matching bug?

**Answer:** Not necessarily. This may be an object-level authorization flaw (IDOR/BOLA). Enforce owner/tenant checks from server data at the service layer.

**Ex 11.** An API uses a catch-all `permitAll()` matcher in the chain just so static resources load. What is the right fix?

**Answer:** Identify exact public static paths, apply `permitAll()` only to them, and keep other paths protected or denied. Do not bypass the entire `FilterChainProxy` if security headers/filters are needed.

**Ex 12.** `GET /api/records/7/export` returns 403; can you tell for sure whether the API chain or fallback chain blocked it?

**Answer:** Not yet. HTTP status alone does not name the chain. When chain order needs verification, use test instrumentation or safe logging to confirm which request matchers/chains were invoked; positive cases also verify wiring.

## 15. Conclusion

To detect **protection gaps caused by request matching**, do not test only valid paths. Always verify:

~~~text
Explicitly declared public routes
+ Protected routes/methods with clear permission conditions
+ SecurityFilterChain coverage, including catch-all
+ Deny-by-default across every scope requiring protection
+ Positive and negative identity tests
+ Negative path/method/alias tests
+ Real HTTP tests for proxies, encoded paths, and context/servlet paths
+ Regression gate when new routes appear
+ Service/object-level authorization where needed
~~~

**Key takeaway:** `anyRequest().denyAll()` covers only requests that **entered the right SecurityFilterChain**; an HTTP 404 from a missing controller **does not prove** authorization ran. Combining positive tests, negative-path tests, real filter-chain tests, and real HTTP/proxy tests catches secondary paths before they turn into vulnerabilities.