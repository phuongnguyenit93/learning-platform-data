# Checking Security Headers, Redirects, and JSON Error Structure

## Learning Objectives

This lesson belongs to **HTTP Testing** in **Spring Security reactive (Spring WebFlux)**. After completing it, you will be able to:

1. Use `WebTestClient` to verify **status + response headers + JSON body**, rather than asserting HTTP 200 alone.
2. Distinguish Spring Security's **default security headers** (`Cache-Control`, `X-Content-Type-Options`, `X-Frame-Options`, HSTS over HTTPS) from policies that **must be explicitly configured**, such as Content-Security-Policy (CSP).
3. Test **redirects** for unauthenticated browser requests: 3xx, `Location`, same-origin, rejecting untrusted return URLs, and not confusing them with 401 JSON APIs.
4. Verify an API returns **`application/problem+json`** with `type/title/status/detail/instance` fields and a stable business error `code`, covering 400, 401, 403, and 404 errors.
5. Understand the differences among `ServerAuthenticationEntryPoint` (unauthenticated), `ServerAccessDeniedHandler` (authenticated but insufficient privilege), `@RestControllerAdvice` (business errors), and the global WebFlux error handler.
6. Separate two `SecurityWebFilterChain`s: a Bearer JWT API **returning JSON** and browser routes **redirecting to login**, plus a deny-all fallback for out-of-scope routes.
7. Write a Java 17 + Spring Boot 3.5 demo using `mockJwt()` / `mockUser()` to test HTTP authorization, while understanding that mock JWTs **do not verify real JWT signatures**.
8. Test the HTTP/HTTPS boundary for HSTS, `WWW-Authenticate` for Bearer, zero token/stack-trace leakage in error bodies, and CSRF in apps with browser cookies/sessions.
9. Design **less brittle** tests: compare headers semantically, use JSONPath instead of full JSON string matching, while still asserting exact location/status/code when part of the public contract.

> **Scope:** Reactive Spring Security with `SecurityWebFilterChain`, `ServerHttpSecurity`, and `WebTestClient`; not Servlet `MockMvc`/`HttpSecurity`. The browser route example illustrates **unauthenticated redirects** without integrating a full authentication UI (OIDC/form login). API routes use an OAuth2 JWT Resource Server; `mockJwt` tests focus on the HTTP contract, while JWS/JWKS/issuer/audience require dedicated integration tests.

## 1. Why is checking only the status code not enough?

An API can return HTTP 401 and still suffer from security flaws:

- Returning an HTML `/login` redirect instead of JSON, breaking REST clients trying to read the error.
- Returning JSON `{"error":"Invalid token abc.def.ghi"}`, leaking the Bearer token in logs or responses.
- Missing `Cache-Control: no-store` on responses containing sensitive data.
- Missing `X-Content-Type-Options: nosniff` when clients/browsers might sniff MIME types.
- Missing CSP on HTML pages with embedded script content or unwanted framing.
- Returning 403 for unauthenticated callers when the app standard is 401, or 302 for non-browser APIs.
- Inconsistent error JSON schemas depending on where the error occurred: 401 from the security filter differs from 400 from a controller.
- Taking redirect `Location` from `returnUrl=https://attacker.example`, causing an open redirect.
- Asserting HSTS over localhost HTTP and assuming the framework is broken, even though HSTS is only sent over **HTTPS**.

Good testing places a **contract** across three layers:

~~~text
HTTP Response
  |
  ├─ Status code: 200/302/400/401/403/404/500
  ├─ Headers:
  |     Content-Type
  |     Cache-Control
  |     X-Content-Type-Options
  |     X-Frame-Options
  |     Content-Security-Policy
  |     Strict-Transport-Security (HTTPS)
  |     WWW-Authenticate (if 401 per HTTP auth)
  |     Location (if 3xx)
  |
  └─ Body:
        Successful DTO
        Or problem JSON with an agreed schema
~~~

Do not blindly assert every header on every response from a static checklist. Security headers are **contextual**: HTML differs from JSON; static assets may be cacheable; HSTS applies to HTTPS; redirects serve browsers rather than always fitting APIs.

## 2. Key security headers table in Spring Security WebFlux

Spring Security 6.5 enables several default security response headers. Some can be altered/overridden by the application. Always read the **actual security chain configuration** and test real behavior.

| Header | Example / expectation | Purpose and notes |
|---|---|---|
| `Cache-Control` | Contains `no-store` for private data/auth errors | Prevents caching sensitive responses. Defaults typically include `no-cache, no-store, max-age=0, must-revalidate`; apps may override. |
| `Pragma` | `no-cache` (if policy uses it) | Legacy HTTP cache compatibility; does not replace `Cache-Control`. |
| `Expires` | `0` or policy value | Cache-related; avoid asserting if reverse proxies manage it and the contract does not require it. |
| `X-Content-Type-Options` | `nosniff` | Mitigates certain MIME sniffing; does not replace verifying real `Content-Type`. |
| `X-Frame-Options` | `DENY` by default | Reduces clickjacking by blocking framing; may be `SAMEORIGIN` per policy. |
| `Strict-Transport-Security` | `max-age=...` **over HTTPS** | HSTS applies to secure responses; verify TLS/proxy configuration rather than forcing it on plain HTTP. |
| `X-XSS-Protection` | `0` in modern default configs | Legacy header for retired XSS Auditors; never use instead of CSP/escaping. |
| `Content-Security-Policy` | `default-src 'self'; object-src 'none'`, page-dependent | **Not added by Spring by default**: applications must design an appropriate policy. |
| `Referrer-Policy` | e.g., `strict-origin-when-cross-origin` | Configuration-dependent; do not assume it is always present by default. |
| `Permissions-Policy` | Restricts camera/microphone/geolocation... | Requires explicit policy; header support varies by stack/proxy. |
| `WWW-Authenticate` | e.g., `Bearer realm="api"` | Authentication challenge on 401 for Bearer APIs, distinct from X-Frame/CSP. |
| `Location` | `/web/login` or same-origin URL | Only for redirect responses; must block open redirects. |

**Do not confuse two headers:** `Content-Type: application/json` describes the body; `X-Content-Type-Options: nosniff` tells browsers not to guess MIME types beyond what is declared. When an API uses RFC Problem Details, the proper `Content-Type` is `application/problem+json`.

### 2.1. Assert exact values, not just header presence

Use `WebTestClient.expectHeader()`:

~~~java
client.get().uri("/api/public")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .valueEquals("X-Content-Type-Options", "nosniff")
    .expectHeader()
        .valueEquals("X-Frame-Options", "DENY");
~~~

This is a **test fragment**; it requires a `client` bound to the Spring context. Simply calling `exists("X-Frame-Options")` is insufficient: the value could be `SAMEORIGIN` when policy requires `DENY`. Where security policies may validly evolve, choose meaningful assertions aligned with the architecture.

### 2.2. Check `Cache-Control` by directive

You do not always need to match the entire string `no-cache, no-store, max-age=0, must-revalidate` because directive order/values can change across proxies or specific responses. For private endpoints requiring `no-store`:

~~~java
.expectHeader().value("Cache-Control", value ->
    assertTrue(value.contains("no-store")));
~~~

This is a test fragment; import `assertTrue`. If the application overrides `Cache-Control` to cache static assets, do not force assets to return `no-store` against performance needs. However, **never** accidentally allow private profiles, tokens, or error details to sit in shared caches.

### 2.3. HSTS: requires an HTTPS context

HSTS is sent when the application treats the request as secure. In an in-memory test over `http://localhost`, a test asserting **no HSTS** can be right. You can simulate an HTTPS request via `WebTestClient.mutate().baseUrl("https://localhost").build()`; behind a real proxy, run integration tests for TLS/`ForwardedHeaderTransformer` within the proper trust boundary.

**Never attach `X-Forwarded-Proto: https` from a client and treat it as trusted HTTPS.** The backend must trust forwarded headers **only from approved proxies**; attackers must not be able to spoof HTTPS or `Host` via raw headers.

Likewise, do not enable HSTS `includeSubDomains/preload` in a demo without verifying every subdomain supports HTTPS. Preloading is a domain-wide policy change requiring review.

### 2.4. CSP is not added automatically

For a pure JSON API, a strict policy such as:

~~~http
Content-Security-Policy: default-src 'none'; object-src 'none'; frame-ancestors 'none'
~~~

can be fitting, though CSP primarily acts in **browsers**. For HTML UIs using scripts/styles and CDNs, craft an appropriate policy rather than copying `default-src 'none'` and breaking the page.

Spring Security WebFlux DSL:

~~~java
.headers(headers -> headers.contentSecurityPolicy(
    policy -> policy.policyDirectives(
        "default-src 'self'; object-src 'none'; frame-ancestors 'none'")))
~~~

This is a `ServerHttpSecurity` fragment, not a Servlet header writer. CSP does not replace HTML escaping, input validation, or other clickjacking defenses.

## 3. Testing redirects: HTTP 3xx must carry a safe `Location`

### 3.1. Browser routes and API routes can use different entry points

An unauthenticated user visits a browser page:

~~~http
GET /web/private HTTP/1.1
Accept: text/html
~~~

The system may return:

~~~http
HTTP/1.1 302 Found
Location: /web/login
~~~

Meanwhile, a REST client sending:

~~~http
GET /api/reports HTTP/1.1
Accept: application/json
~~~

should receive:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
WWW-Authenticate: Bearer realm="api"
~~~

**Do not force both to share the same failure response.** Browsers expect navigation; APIs want machine-readable statuses and JSON. Using a default `formLogin` chain for APIs easily causes APIs to receive HTML login redirects instead of 401.

### 3.2. Assert more than just 3xx

~~~java
client.get().uri("/web/private")
    .exchange()
    .expectStatus().is3xxRedirection()
    .expectHeader().value("Location", value -> {
        java.net.URI uri = java.net.URI.create(value);
        assertEquals("/web/login", uri.getPath());
        assertTrue(uri.getHost() == null
            || uri.getHost().equals("localhost"));
    });
~~~

This is a test fragment. Check the **target path** and **origin/host** so a test does not pass on 302 while actually redirecting to another domain. Some redirect strategies emit absolute URIs rather than relative ones, so parsing with `java.net.URI` is safer than manual string checks.

If the contract mandates 302, use `isEqualTo(HttpStatus.FOUND)`. If the flow permits multiple valid 3xx codes depending on the redirect strategy, use `is3xxRedirection()` and assert `Location`. Distinguish **302/303/307/308** for post-POST redirects because they govern whether clients preserve or change the HTTP method; do not lump everything together blindly.

### 3.3. Preventing open redirects

A flawed design takes the URL directly from the caller:

~~~http
GET /web/private?next=https://evil.example/collect
~~~

and responds:

~~~http
Location: https://evil.example/collect
~~~

If `next`/`returnUrl` exists, the backend must validate against an origin/path allowlist or accept only canonicalized relative local paths. Never trust raw `Host` or `X-Forwarded-Host` as the redirect domain. Tests should send `next=https://evil.example` and verify `Location` stays on an allowed origin.

### 3.4. `WebTestClient` tests do not equal a real browser

`WebTestClient` tests HTTP responses by default without browser UI, history, or JavaScript. A 3xx test should assert the **initial response** and `Location`; to test the login page itself, issue a separate GET to the login URL and assert 200. Browser automation is needed only when verifying live cookies/`SameSite`/CSP or end-to-end OIDC provider redirect flows.

### 3.5. Form login, OAuth2 Login, and custom redirects

Entry points can vary:

- `RedirectServerAuthenticationEntryPoint`: redirects to a configured URL, fitting browser navigation models.
- Form login: typically routes to a login page/redirect when configured; failure and success URLs should also be tested.
- OAuth2 Login: may redirect to an Authorization Server with state/nonce/PKCE; verify allowlisted redirect URIs and CSRF state without asserting a fixed random state value.
- JSON API entry point: returns 401, no `Location`.
- API missing scope: returns 403 JSON, no redirect.

When OIDC/OAuth2 redirects are dynamic, assert **scheme/host/path, required query keys**, and the presence/correlation of `state`, rather than snapshotting random `state` strings.

## 4. Error JSON: designing a testable contract

This lab uses a body **aligned with RFC 9457 Problem Details**:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required.",
  "instance": "/api/reports",
  "code": "AUTH_REQUIRED"
}
~~~

Meaning:

| Field | Purpose | Test condition |
|---|---|---|
| `type` | URI identifying the problem type; `about:blank` is default | Matches URI/string contract |
| `title` | Short error type summary | Does not leak raw exceptions |
| `status` | HTTP status in body, matching response status | Corresponding 401/403/400/404 |
| `detail` | Safe user-facing explanation | Contains no tokens/stack traces/DB queries |
| `instance` | URI/path where error occurred | Does not echo query secrets |
| `code` | Application-specific extension field | Stable machine-readable error code |

RFC 9457 allows extension members such as `code`. **There is no universal rule** requiring every API to use `AUTH_REQUIRED`/`ACCESS_DENIED`; these are the contract chosen for this lesson.

### 4.1. Keeping errors consistent across security filters and controllers

A typical `@RestControllerAdvice` handles exceptions from controllers/services, **not 401/403 errors from Spring Security filters**. Distinguish:

- `ServerAuthenticationEntryPoint`: unauthenticated requests, produces **401** (usually with `WWW-Authenticate` for Bearer).
- `ServerAccessDeniedHandler`: authenticated but lacking privilege, produces **403**.
- `@ExceptionHandler`/`@RestControllerAdvice`: validation/business errors (e.g., 400, 404) inside controllers.
- `ErrorWebExceptionHandler`: broader WebFlux error boundary for normalizing all errors.
- Resource Server Bearer-specific handlers may emit `WWW-Authenticate` themselves; if customized, preserve required HTTP auth protocol details.

**Important:** Wrapping a controller in try/catch will not catch 401/403 responses returned by `SecurityWebFilterChain` before the request reaches the controller.

### 4.2. 401 differs from 403

| Scenario | Expected | Avoid |
|---|---|---|
| Missing Bearer token on protected API | 401 JSON + Bearer challenge | 302 HTML login |
| JWT with wrong signature/issuer/audience/expired | 401 (per auth failure flow) | Leaking token/technical errors |
| Valid JWT missing scope | 403 JSON, optionally `insufficient_scope` challenge | 401 causing infinite client re-login loops |
| Authenticated, lacking business permission | 403 JSON | Empty 200 or admin fallback |
| Bad input/validation | Consistent 400 JSON | Returning full stack trace |
| Resource does not exist | Consistent 404 JSON | Revealing existence of another user's private resource |

For Bearer, `WWW-Authenticate: Bearer realm="api"` on 401 is a challenge; 403 due to scope may use `Bearer error="insufficient_scope"` per RFC 6750. Never log or echo raw tokens into challenges, `detail`, or response bodies.

### 4.3. Assert both body and headers

A thorough test:

~~~java
client.get().uri("/api/reports")
    .exchange()
    .expectStatus().isUnauthorized()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/problem+json"))
    .expectHeader().valueEquals(
        "WWW-Authenticate", "Bearer realm=\"api\"")
    .expectHeader().doesNotExist("Location")
    .expectBody()
    .jsonPath("$.status").isEqualTo(401)
    .jsonPath("$.code").isEqualTo("AUTH_REQUIRED")
    .jsonPath("$.type").isEqualTo("about:blank");
~~~

This is a test fragment; the complete lab code appears below. **Do not compare full JSON strings** because key order is not part of the JSON contract. However, when the body guarantees a fixed `code`, assert that exact code value.

### 4.4. Avoid unsafe error responses

Never return:

~~~json
{
  "detail": "Signature failed for Bearer eyJhbGciOi...",
  "exception": "org.springframework.security.oauth2...",
  "stackTrace": "...",
  "sql": "SELECT * FROM accounts WHERE ..."
}
~~~

Besides leaking secrets, such details enable enumeration and help attackers analyze the stack. Internal logs can record a correlation ID, route, sanitized reason code, and safe trace. Never let `instance` include raw query strings when queries might contain secrets.

### 4.5. Response already committed issue

In reactive `ServerHttpResponse`, set status and headers **before** returning the body-writing publisher; never call `block()`/`subscribe()` manually. Once a response is committed, never try to write a second JSON body or retroactively change status to 401; that is a pipeline bug. Security handlers must run while the response is still writable.

## 5. Spring Boot WebFlux Lab: Problem JSON API and browser redirects

Java 17 + Spring Boot 3.5.16 example, comprising:

- API routes `/api/**`: OAuth2 JWT Resource Server; public GETs, GET reports requiring `SCOPE_reports.read`, GET admin requiring `SCOPE_admin.read`.
- API 401/403 returning `application/problem+json` with `WWW-Authenticate` when applicable, `Cache-Control: no-store`, and no `Location`.
- GET `/api/validate?limit=0` returning 400 and GET `/api/items/missing` returning 404 via `@RestControllerAdvice` with the **exact same JSON schema**.
- Browser routes `/web/**`: unauthenticated GET `/web/private` redirects to `/web/login` without returning Problem JSON. This simulates an entry point only: **a full login system is not implemented**.
- `/web/login` is public; `/web/private` requires Authentication.
- A final catch-all chain uses deny-all so URLs matching neither chain never become public.
- Each chain configures its own CSP policy; Spring Security retains default security headers.

### 5.1. Directory structure

~~~text
http-security-tests/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/HttpContractApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/HttpContractTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'http-security-tests'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

JDK 17+ and a compatible Gradle/Gradle Wrapper. Pure WebFlux demo—no Servlet `spring-boot-starter-web` and no database needed.

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - reports-api
~~~

The issuer/JWKS URLs above are **placeholders**; replace with a real HTTPS IdP to validate Bearer JWTs in production. Providing both `issuer-uri` and `jwk-set-uri` supplies the key URI without requiring discovery at startup; signature/issuer/audience validation remains the JWT decoder's job upon receiving a token. `mockJwt()` in unit tests does not exercise those validations.

### 5.2. Complete application

File `src/main/java/example/HttpContractApplication.java`:

~~~java
package example;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class HttpContractApplication {

    private static final MediaType PROBLEM_JSON =
        MediaType.parseMediaType("application/problem+json");

    public static void main(String[] args) {
        SpringApplication.run(HttpContractApplication.class, args);
    }

    public record ProblemDocument(
        String type,
        String title,
        int status,
        String detail,
        String instance,
        String code) {
    }

    static ProblemDocument problemDocument(
        HttpStatus status, String detail, String path, String code) {

        return new ProblemDocument(
            "about:blank",
            status.getReasonPhrase(),
            status.value(),
            detail,
            path,
            code);
    }

    // Security handlers operate BEFORE controller advice.
    static Mono<Void> writeSecurityProblem(
        ServerWebExchange exchange,
        ObjectMapper mapper,
        HttpStatus status,
        String detail,
        String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(PROBLEM_JSON);
        response.getHeaders().setCacheControl("no-store");

        if (status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\"");
        }
        else if (status == HttpStatus.FORBIDDEN) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer error=\"insufficient_scope\"");
        }

        var body = problemDocument(
            status,
            detail,
            exchange.getRequest().getPath().value(),
            code);

        return Mono.fromCallable(() ->
                mapper.writeValueAsBytes(body))
            .flatMap(bytes -> response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes))));
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain api(
        ServerHttpSecurity http, ObjectMapper mapper) {

        ServerAuthenticationEntryPoint entryPoint =
            (exchange, error) -> writeSecurityProblem(
                exchange, mapper,
                HttpStatus.UNAUTHORIZED,
                "Authentication is required.",
                "AUTH_REQUIRED");

        ServerAccessDeniedHandler deniedHandler =
            (exchange, error) -> writeSecurityProblem(
                exchange, mapper,
                HttpStatus.FORBIDDEN,
                "Insufficient permission.",
                "ACCESS_DENIED");

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"))
            // Only valid for Bearer-only APIs, NOT using session cookies.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(policy -> policy
                    .policyDirectives(
                        "default-src 'none'; object-src 'none'; "
                        + "frame-ancestors 'none'")))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/validate")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/items/*")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_admin.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/web/**"))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            // Login UI is a demo; real form login is not enabled.
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(policy -> policy
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; "
                        + "frame-ancestors 'none'")))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new RedirectServerAuthenticationEntryPoint(
                        "/web/login")))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/web/login")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/web/private")
                    .authenticated()
                .anyExchange().denyAll())
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain denyOtherRoutes(ServerHttpSecurity http) {
        return http
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll())
            .build();
    }

    static class InvalidLimit extends RuntimeException {
    }

    static class ItemMissing extends RuntimeException {
    }

    @RestController
    public static class Endpoints {

        @GetMapping("/api/public")
        public Mono<Map<String, String>> publicApi() {
            return Mono.just(Map.of("message", "public"));
        }

        @GetMapping("/api/reports")
        public Mono<Map<String, String>> reports() {
            return Mono.just(Map.of("report", "available"));
        }

        @GetMapping("/api/admin")
        public Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("admin", "ok"));
        }

        @GetMapping("/api/validate")
        public Mono<Map<String, Integer>> validate(
            @RequestParam int limit) {

            if (limit < 1 || limit > 100) {
                return Mono.error(new InvalidLimit());
            }
            return Mono.just(Map.of("limit", limit));
        }

        @GetMapping("/api/items/{id}")
        public Mono<Map<String, String>> item(
            @PathVariable String id) {

            if (!"visible".equals(id)) {
                return Mono.error(new ItemMissing());
            }
            return Mono.just(Map.of("id", id));
        }

        @GetMapping(
            value = "/web/login",
            produces = MediaType.TEXT_PLAIN_VALUE)
        public Mono<String> login() {
            return Mono.just("Demo login page");
        }

        @GetMapping(
            value = "/web/private",
            produces = MediaType.TEXT_PLAIN_VALUE)
        public Mono<String> privatePage() {
            return Mono.just("Private browser page");
        }
    }

    @RestControllerAdvice
    public static class ApiErrors {

        @ExceptionHandler(InvalidLimit.class)
        public ResponseEntity<ProblemDocument> invalidLimit(
            ServerWebExchange exchange) {

            return businessProblem(
                exchange, HttpStatus.BAD_REQUEST,
                "limit must be between 1 and 100.",
                "INVALID_LIMIT");
        }

        @ExceptionHandler(ItemMissing.class)
        public ResponseEntity<ProblemDocument> itemMissing(
            ServerWebExchange exchange) {

            return businessProblem(
                exchange, HttpStatus.NOT_FOUND,
                "Requested item does not exist.",
                "ITEM_NOT_FOUND");
        }

        private ResponseEntity<ProblemDocument> businessProblem(
            ServerWebExchange exchange,
            HttpStatus status, String detail, String code) {

            return ResponseEntity.status(status)
                .contentType(PROBLEM_JSON)
                .cacheControl(CacheControl.noStore())
                .body(problemDocument(
                    status,
                    detail,
                    exchange.getRequest().getPath().value(),
                    code));
        }
    }
}
~~~

### 5.3. Why are there two security chains and one fallback?

- `@Order(1)` for `/api/**` handles Bearer/JWT and Problem JSON.
- `@Order(2)` for `/web/**` handles browser navigation, redirecting unauthenticated users to `/web/login`.
- `@Order(3)` deny-all prevents out-of-scope URLs from slipping past when no chain matches.
- When multiple `SecurityWebFilterChain`s exist, **the first matching chain is used**; do not assume a request runs through all 3 chains.
- The API chain disables formLogin/Basic and uses a custom entry point and access denied handler. The browser chain does not use the API JSON entry point.
- API error handlers are configured in both `exceptionHandling` and the OAuth2 Resource Server DSL so there is no unexpected discrepancy between "no credentials" and failed Bearer authentication.
- `@RestControllerAdvice` handles 400/404 from controllers without trying to catch 401/403 from Spring Security filters.
- Each chain configures its own CSP; other default security headers remain active since `headers().disable()` is not called.
- CSRF is disabled **only on the Bearer-only API**. The browser chain keeps CSRF enabled by default; if POST forms/cookie login are added, add `csrf()` tests.

### 5.4. How JSON is written in the reactive security handler

Inside `writeSecurityProblem(...)`:

1. Set status before the response is committed.
2. Set `Content-Type` to `application/problem+json`.
3. Set `Cache-Control` to `no-store`.
4. Set `WWW-Authenticate` appropriately for Bearer 401/403 in the lab.
5. Build `ProblemDocument` with a stable code and path, **never** copying raw tokens/query strings/exceptions.
6. Use Jackson `ObjectMapper.writeValueAsBytes(...)` inside `Mono.fromCallable` and `response.writeWith(Mono.just(...))`.
7. Never call `block()` or `subscribe()` manually.
8. Use `response.bufferFactory().wrap(bytes)` to create a `DataBuffer`; the reactive server manages writing and completion.

This pattern suits small error bodies. Production should centralize an error-code registry, correlation IDs, telemetry, exception mapping, and serialization failure handling, never writing a second response after commit.

### 5.5. Expected HTTP contract

| Request | Authentication | Expected status | Content-Type / Location | `code` |
|---|---|---:|---|---|
| GET `/api/public` | Anonymous | 200 | `application/json` | No problem |
| GET `/api/reports` | Anonymous | 401 | `application/problem+json`; **no** `Location` | `AUTH_REQUIRED` |
| GET `/api/reports` | JWT missing `reports.read` | 403 | `application/problem+json` | `ACCESS_DENIED` |
| GET `/api/reports` | JWT with `reports.read` | 200 | `application/json` | No problem |
| GET `/api/admin` | JWT with only `reports.read` | 403 | `application/problem+json` | `ACCESS_DENIED` |
| GET `/api/admin` | JWT with `admin.read` | 200 | `application/json` | No problem |
| GET `/api/validate?limit=0` | Anonymous | 400 | `application/problem+json` | `INVALID_LIMIT` |
| GET `/api/items/missing` | Anonymous | 404 | `application/problem+json` | `ITEM_NOT_FOUND` |
| GET `/web/private` | Anonymous | 3xx | `Location` pointing to `/web/login` | No Problem JSON |
| GET `/web/login` | Anonymous | 200 | `text/plain` | No problem |
| GET `/web/private` | mock authenticated | 200 | `text/plain` | No problem |

The table above reflects **expected behavior** from the code, not a claim of execution. Browser routes do not have a real login flow yet. The JWT-protected API also requires a real issuer/JWKS when not using test mocks.

## 6. `WebTestClient` integration tests for HTTP contracts

File `src/test/java/example/HttpContractTest.java`:

~~~java
package example;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class HttpContractTest {

    @Autowired
    WebTestClient client;

    private WebTestClient withScope(String scope) {
        return client.mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_" + scope)));
    }

    @Test
    void publicApiReturns200AndJson() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void defaultNosniffAndFrameDenyArePresent() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY");
    }

    @Test
    void cspWasConfiguredForTheApi() {
        client.get().uri("/api/public")
            .exchange()
            .expectHeader().value(
                "Content-Security-Policy", csp -> {
                    assertTrue(csp.contains(
                        "default-src 'none'"));
                    assertTrue(csp.contains(
                        "frame-ancestors 'none'"));
                });
    }

    @Test
    void successfulApiResponseIsNotStoredInSharedCache() {
        client.get().uri("/api/public")
            .exchange()
            .expectHeader().value(
                HttpHeaders.CACHE_CONTROL,
                value -> assertTrue(
                    value.contains("no-store")));
    }

    @Test
    void hstsIsAbsentForPlainHttpRequest() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                "Strict-Transport-Security");
    }

    @Test
    void hstsIsPresentOnMockHttpsRequest() {
        WebTestClient secureClient = client.mutate()
            .baseUrl("https://localhost").build();

        secureClient.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().value(
                "Strict-Transport-Security",
                value -> assertTrue(value.contains("max-age=")));
    }

    @Test
    void anonymousApiGets401ProblemAndBearerChallenge() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\"")
            .expectHeader().doesNotExist(
                HttpHeaders.LOCATION)
            .expectBody()
            .jsonPath("$.type").isEqualTo("about:blank")
            .jsonPath("$.title").isEqualTo("Unauthorized")
            .jsonPath("$.status").isEqualTo(401)
            .jsonPath("$.code").isEqualTo("AUTH_REQUIRED")
            .jsonPath("$.instance").isEqualTo("/api/reports");
    }

    @Test
    void error401IsExplicitlyNotCached() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(
                HttpHeaders.CACHE_CONTROL,
                value -> assertTrue(
                    value.contains("no-store")));
    }

    @Test
    void insufficientScopeGets403ProblemNotRedirect() {
        withScope("other.read")
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectHeader().doesNotExist(HttpHeaders.LOCATION)
            .expectBody()
            .jsonPath("$.status").isEqualTo(403)
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
            .jsonPath("$.instance").isEqualTo("/api/reports");
    }

    @Test
    void reportsScopeGrantsReportsEndpoint() {
        withScope("reports.read")
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("available");
    }

    @Test
    void reportScopeDoesNotGrantAdminAccess() {
        withScope("reports.read")
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void adminScopeCanAccessAdminRoute() {
        withScope("admin.read")
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.admin").isEqualTo("ok");
    }

    @Test
    void anonymousBrowserRouteRedirectsToLocalLogin() {
        client.get().uri("/web/private")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(
                HttpHeaders.LOCATION, value -> {
                    URI target = URI.create(value);
                    assertEquals("/web/login", target.getPath());
                    assertTrue(target.getHost() == null
                        || target.getHost().equals("localhost"));
                });
    }

    @Test
    void untrustedNextParameterCannotChangeRedirectOrigin() {
        client.get().uri(
            "/web/private?next=https://evil.example/steal")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(
                HttpHeaders.LOCATION, value -> {
                    URI target = URI.create(value);
                    assertEquals("/web/login", target.getPath());
                    assertFalse(value.contains("evil.example"));
                });
    }

    @Test
    void browserLoginPageIsPublic() {
        client.get().uri("/web/login")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("Demo login page");
    }

    @Test
    void authenticatedBrowserRequestDoesNotRedirect() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/web/private")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(HttpHeaders.LOCATION)
            .expectBody(String.class)
            .isEqualTo("Private browser page");
    }

    @Test
    void businessValidationErrorUsesSameProblemShape() {
        client.get().uri("/api/validate?limit=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectBody()
            .jsonPath("$.type").isEqualTo("about:blank")
            .jsonPath("$.status").isEqualTo(400)
            .jsonPath("$.code").isEqualTo("INVALID_LIMIT")
            .jsonPath("$.instance").isEqualTo("/api/validate");
    }

    @Test
    void missingBusinessResourceUses404Problem() {
        client.get().uri("/api/items/missing")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectBody()
            .jsonPath("$.status").isEqualTo(404)
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void errorInstanceDoesNotEchoSensitiveQuery() {
        client.get().uri(
            "/api/validate?limit=0&token=do-not-echo")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.instance").isEqualTo("/api/validate");
    }

    @Test
    void errorBodyDoesNotExposeExceptionOrToken() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody(String.class)
            .consumeWith(result -> {
                String body = result.getResponseBody();
                assertNotNull(body);
                assertFalse(body.contains("stackTrace"));
                assertFalse(body.contains("exception"));
                assertFalse(body.contains("Bearer "));
            });
    }
}
~~~

### 6.1. Running tests

~~~bash
gradle test
~~~

If using the wrapper: `./gradlew test` (Linux/macOS) or `gradlew.bat test` (Windows). The class above has **20 test methods**. They are **designed to pass** with compatible Spring Boot 3.5.x/Spring Security 6.5.x; you must still run the build/tests in a real environment to observe actual results. This lesson does not claim the tests were executed during authoring.

### 6.2. Why do HSTS tests use two different requests?

- `hstsIsAbsentForPlainHttpRequest`: verifies that a plain HTTP mock request **does not** emit HSTS. This is not a bug.
- `hstsIsPresentOnMockHttpsRequest`: creates a `WebTestClient` with an HTTPS base URL to simulate a secure request, then asserts HSTS contains `max-age=`.
- Behind a production reverse proxy, **real end-to-end TLS tests** are needed to confirm which layer inserts HSTS and which scheme the backend observes. Do not merely spoof `X-Forwarded-Proto` via a client-supplied header.
- If the app or gateway overrides security headers, expected tests must verify the contract **across the entire proxy path**, not only an in-memory mock.

### 6.3. Why aren't `mockJwt()`/`mockUser()` full authentication tests?

`mockJwt()` places a `JwtAuthenticationToken` into the test security context with explicit authorities. It skips signature, `iss`, `aud`, expiry, and the JWKS decoder. This lesson verifies response contracts after authorization, **not token issuance/validation**.

Similarly, `mockUser()` proves that the browser route requires an authenticated principal and stops redirecting when given a mock Authentication—it does **not** prove form login/OIDC/cookies work. When implementing real login, add tests for login, session fixation, cookie flags, CSRF, logout, and refresh flows.

### 6.4. Why assert with JSONPath instead of the full body?

JSON objects have no semantic key ordering. Avoid testing:

~~~java
// ANTI-PATTERN: easily fails if key ordering changes.
expectBody(String.class).isEqualTo(
    "{\"code\":\"AUTH_REQUIRED\",\"status\":401}");
~~~

Real JSON may also contain `type/title/detail/instance`. Use `jsonPath("$.code").isEqualTo(...)` and `jsonPath("$.status").isEqualTo(...)` to check the contract. If the API requires a sensitive field to be **absent**, use JSONPath `doesNotExist()` or parse the JSON tree to assert absence; in the demo, checking that the raw body lacks exception/token strings is simply an extra sanity check.

### 6.5. Asserting 401 vs 403 in context

Some applications require different authentication behaviors across chains: unauthenticated browser 302, API missing Bearer 401, authenticated missing scope 403. Testing **the same URL with three identities** catches regressions:

~~~text
GET /api/reports, no token               → 401 problem JSON
GET /api/reports, mock JWT scope=other   → 403 problem JSON
GET /api/reports, mock JWT scope=reports → 200 JSON
~~~

Similarly for browsers:

~~~text
GET /web/private, anonymous             → 3xx Location=/web/login
GET /web/private, authenticated         → 200 text/plain
GET /web/login, anonymous               → 200 text/plain
~~~

These are expected contract tables, not observed live HTTP output.

## 7. Testing JSON errors across application layers

### 7.1. Security and business errors must share one JSON contract

In the lab:

~~~text
Request
  |
  ├─ SecurityWebFilterChain
  |      ├─ ServerAuthenticationEntryPoint → 401 ProblemDocument
  |      └─ ServerAccessDeniedHandler      → 403 ProblemDocument
  |
  └─ Controller / service
         ├─ @ExceptionHandler(InvalidLimit) → 400 ProblemDocument
         └─ @ExceptionHandler(ItemMissing)  → 404 ProblemDocument
~~~

This is why you must test 400, 401, 403, and 404. If you test only controller advice, security filters might still emit default HTML. If you test only filters, validation errors might return a completely different schema.

### 7.2. How to test 500 without leaking sensitive details

In production, you can define a standard response:

~~~json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected error occurred.",
  "instance": "/api/example",
  "code": "INTERNAL_ERROR"
}
~~~

Never emit raw exception messages, stack traces, SQL, or credentials. Still, never catch every `Throwable` and swallow errors as 200; ensure monitoring receives failure signals and returns HTTP 500. For a consistent contract, test the behavior of the active `ErrorWebExceptionHandler`/Spring Boot error handling. **The lab does not install a custom 500 fallback**, so it does not guarantee every unexpected exception follows the demo schema.

### 7.3. JSON serialization and safety

Use the application's configured Jackson/`ObjectMapper`, rather than concatenating JSON strings from `exception.getMessage()`. `ProblemDocument` uses explicit field names/values; `instance` uses the framework-parsed request path without echoing query params. Serialization ensures quotes and control characters are escaped safely.

### 7.4. Note on `WWW-Authenticate`

Per RFC 6750, Bearer APIs should send an appropriate challenge on 401; 403 due to missing scope may supply `insufficient_scope`. The lab keeps it simple:

~~~http
WWW-Authenticate: Bearer realm="api"
~~~

and:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

However, a real app may use `BearerTokenServerAuthenticationEntryPoint` and `BearerTokenServerAccessDeniedHandler` to generate challenges from OAuth2 error codes. If you replace them with custom JSON handlers, test both HTTP auth headers and JSON bodies.

## 8. Testing redirects in OIDC/OAuth2 and after POST

The lab only redirects to `/web/login`. With real OAuth2 login, redirects typically look like:

~~~text
/oauth2/authorization/<registrationId>
    → IdP authorization endpoint
       ?response_type=code
       &client_id=...
       &redirect_uri=...
       &scope=...
       &state=<random>
       [&code_challenge=...]
~~~

This is a diagram, not a directly runnable URL. Tests should:

- Verify `Location` uses an **approved issuer/authorization host**, not a domain from untrusted input.
- Verify `response_type=code`, `state` is present and non-empty, and `redirect_uri` is strictly on the allowlist.
- For PKCE, verify a valid `code_challenge` and method when required; never assert a fixed random challenge value.
- Never log raw authorization codes, `state`/session IDs, or tokens.
- Test that callback requests with wrong/missing or expired state are rejected; prevent CSRF/login CSRF.
- Never let `next`/`returnUrl` parameters turn redirects into open redirects.
- After POST, distinguish 303 (switch to GET per redirect semantics) from 307/308 (preserve method/body), especially for sensitive actions.

When testing with a real browser, verify `Secure`, `HttpOnly`, `SameSite` cookie flags, session rotation, CSRF protection, and logout redirects. Never conclude from a mock `WebTestClient` test that the entire OIDC/SAML/browser flow is tested.

## 9. Common mistakes

**1. Asserting HTTP 200 only:** misses 401, 403, 3xx, security headers, and error body checks.

**2. Assuming CSP is enabled by default:** Spring Security does not add a generic CSP; an explicit policy is required.

**3. Asserting HSTS on plain localhost HTTP:** HSTS applies to HTTPS; test secure requests or real TLS.

**4. Enabling HSTS `preload`/`includeSubDomains` carelessly:** can lock out subdomains lacking HTTPS; review domain policy first.

**5. Asserting only header existence:** `X-Frame-Options: SAMEORIGIN` may violate a `DENY` policy.

**6. Matching the entire `Cache-Control` string in a fixed order:** usually checking `no-store`/`no-cache` directives per contract is sufficient.

**7. Mixing up `Content-Type` and `X-Content-Type-Options`:** they serve different roles.

**8. Disabling all headers with `headers.disable()` to make tests pass:** strips security defaults.

**9. Configuring form login for an API and accepting 302:** REST callers normally expect 401 JSON, not HTML redirects.

**10. Confusing 401 and 403:** unauthenticated → 401; authenticated lacking privilege → 403.

**11. Failing to assert `WWW-Authenticate`:** makes it harder for Bearer clients to handle RFC-compliant challenges.

**12. 3xx whose `Location` points to an attacker domain:** always verify host/origin against open redirects.

**13. Testing only `is3xxRedirection()`:** misses redirects to the wrong path/host.

**14. Snapshotting random OAuth2 redirect `code`/`state`:** brittle and misses real security properties.

**15. Relying on `@RestControllerAdvice` to catch all Spring Security filter errors:** 401/403 usually occur before controllers.

**16. Security handlers returning raw exception messages:** leaks tokens, SQL, and stack traces.

**17. Custom 401 Problem JSON forgetting Bearer challenge:** breaks the HTTP auth contract.

**18. Custom 403 returning `AUTH_REQUIRED` code:** misleads clients into thinking re-login is needed.

**19. Comparing JSON bodies as raw strings:** key order/formatting changes cause false failures; use JSONPath.

**20. Testing `Content-Type: application/json` instead of Problem Details:** `application/problem+json` should be verified accurately.

**21. Testing controller errors only:** misses errors from security chains, gateways, reverse proxies, and decoders.

**22. Using `mockJwt` and concluding JWT signatures are valid:** mocks bypass JWS/JWKS/issuer/audience verification.

**23. Using `mockUser` and concluding the login flow is complete:** only creates a mock Authentication for tests.

**24. Missing a catch-all `SecurityWebFilterChain`:** some URLs may match no chain and be left unprotected.

**25. Multiple chains with wrong `@Order`:** APIs may be redirected by the browser entry point or vice versa.

**26. Putting keys/tokens in query params and echoing `instance`:** query params leak into JSON errors/logs.

**27. Disabling CSRF on browser cookie/session routes:** keep CSRF for unsafe methods.

**28. Asserting HSTS on the app while a proxy strips headers:** test the full production network path.

**29. Adding a CSP without testing real HTML:** browser CSP may break page functionality or remain too permissive.

**30. Substituting local-only tests for staging TLS/redirect/cookie checks:** many issues only surface behind a proxy.

## 10. Checklist for HTTP security test suites

1. Does each endpoint have status checks for anonymous, authenticated-without-privilege, and authorized callers?
2. Do API endpoints missing tokens return 401 JSON, not 302 HTML?
3. Do API endpoints lacking scopes return 403 JSON, rather than forcing re-login?
4. Does `WWW-Authenticate` match the scheme (Basic/Bearer) and error codes?
5. Is the Problem Details `Content-Type` set to `application/problem+json`?
6. Does JSON include `type/title/status/detail/instance/code` with `status` matching the HTTP status?
7. Is JSON free of stackTrace/exception/raw tokens/query secrets?
8. Do 400/404 controller errors and 401/403 security errors share the same schema?
9. Do unexpected 500s return a generic body with correlation/auditing and no stack/SQL leaks?
10. Is `X-Content-Type-Options` set to `nosniff`?
11. Is `X-Frame-Options` `DENY` or `SAMEORIGIN` per policy?
12. Does `Cache-Control` on private endpoints include `no-store`?
13. Is CSP explicit and suited to API vs HTML pages?
14. Is HSTS asserted only over HTTPS, with end-to-end TLS/proxy tests?
15. Are plain HTTP and HTTPS mocks properly distinguished?
16. Are you avoiding treating `X-XSS-Protection` as a replacement for CSP?
17. Do 3xx redirect statuses have a `Location` with the right path and trusted host?
18. Are open redirects prevented across `next`/`returnUrl`, `Host`, and `X-Forwarded-Host`?
19. After POST, do redirects follow proper 302/303/307/308 semantics?
20. Do OAuth2/OIDC redirects validate `state`, PKCE, `redirect_uri`, and issuer allowlists?
21. Is the browser login page public while private pages require authentication?
22. Are CSRF tests present for unsafe methods when browser cookies exist?
23. Are security chain ordering and catch-all deny verified?
24. Do `WebTestClient` tests avoid bypassing login/token flows while claiming authentication was tested?
25. Do signed JWT/JWKS tests complement `mockJwt` authorization tests?
26. Does error mapping avoid changing status/headers after the response is committed?
27. Are negative tests included for malformed headers, invalid bodies, and unknown routes?
28. Were tests run on compatible Gradle/JDK and in staging behind the reverse proxy?

## 11. Self-check

**1.** Does reactive Spring Security add a default `Content-Security-Policy`?

**Answer:** No; the application must configure an appropriate CSP explicitly.

**2.** Does `X-Content-Type-Options: nosniff` mean the response `Content-Type` is JSON?

**Answer:** No. `Content-Type` describes the body; `nosniff` prevents browsers from MIME-sniffing.

**3.** Why shouldn't HSTS be asserted on every local HTTP request?

**Answer:** HSTS is added to secure HTTPS responses; mock HTTP is right to omit HSTS.

**4.** Should an unauthenticated API return 302 or 401?

**Answer:** In the lab's REST contract, return 401 Problem JSON; browser routes redirect.

**5.** What happens when a valid token lacking `reports.read` calls `/api/reports`?

**Answer:** 403 JSON with `code=ACCESS_DENIED`.

**6.** How do you test that a redirect does not go to an attacker domain?

**Answer:** Parse `Location` with `URI`, assert path/host/origin allowlist, and test an untrusted `next` parameter.

**7.** Why is JSONPath less brittle than matching raw JSON strings?

**Answer:** JSON fields have no semantic order; JSONPath checks keys/values per contract.

**8.** Why is `@RestControllerAdvice` insufficient for 401/403 from Spring Security?

**Answer:** Security filters can reject requests before the controller; `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler` are needed.

**9.** Should `exception.getMessage()` be echoed into `detail`?

**Answer:** Not by default, as it can expose credentials/SQL/internal details; use safe generic messages.

**10.** Does `mockJwt()` test signatures, `aud`, or `issuer`?

**Answer:** No. It helps test authorization; signatures/decoders must be tested separately with signed JWTs/JWKS.

**11.** When an unauthenticated browser page redirects, is testing `is3xxRedirection()` alone enough?

**Answer:** No. You must assert a valid `Location` and protection against open redirects.

**12.** If an app uses browser cookies, can it copy the API's `csrf.disable()`?

**Answer:** No. CSRF protection is needed for unsafe methods under a cookie/session threat model.

**13.** Does RFC 9457 Problem Details allow a custom `code` field?

**Answer:** Yes, as an extension member defined by the application's contract.

**14.** Why should 401 Bearer responses test `WWW-Authenticate`?

**Answer:** Because it is the authentication challenge telling clients the scheme/error; custom JSON handlers must not drop protocol requirements.

## References

- Spring Security 6.5 — **Reactive Security HTTP Response Headers**: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security — **Default security headers, HTTPS-only HSTS**: https://docs.spring.io/spring-security/reference/6.5/features/exploits/headers.html
- Spring Security 6.5 — **Reactive Testing Authentication with WebTestClient/mutateWith**: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — **Reactive Testing JWT with mockJwt**: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security 6.5 — **ServerHttpSecurity** and exception handling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 — **RedirectServerAuthenticationEntryPoint** Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationEntryPoint.html
- Spring Security 6.5 — **JWT Resource Server WebFlux**: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Framework — **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — **Error Responses / Problem Details**: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- RFC 9457 — **Problem Details for HTTP APIs**: https://www.rfc-editor.org/rfc/rfc9457
- RFC 6750 — **OAuth 2.0 Bearer Token Usage**: https://www.rfc-editor.org/rfc/rfc6750
- OWASP — **HTTP Headers Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- OWASP — **Unvalidated Redirects and Forwards Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
