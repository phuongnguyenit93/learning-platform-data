# Avoiding Conflicts Between `CorsWebFilter`, WebFlux Configuration, and Spring Security

## 1. Problem Statement and Learning Objectives

An API built with **Spring WebFlux + Spring Security Reactive** is frequently called from a frontend on a different origin. For example, a frontend at `http://localhost:3000` calls an API at `http://localhost:8080`. When the browser reports a **CORS error**, a developer might try adding `@CrossOrigin`, writing `WebFluxConfigurer#addCorsMappings`, registering a `CorsWebFilter`, or calling `ServerHttpSecurity.cors(...)`. Each option exists for a reason, yet enabling them together with inconsistent policies produces unpredictable results: `OPTIONS` preflight returns `401`, the browser rejects an invalid `Access-Control-Allow-Origin`, controller policies have no effect, or production permits more origins than intended.

**Goal of this lesson:** understand **who handles CORS, whether it runs before or after Spring Security, and which policy actually applies to a request**. We will pick one primary configuration, present the alternatives *not to be enabled simultaneously*, and test both allowed and forbidden origins.

By the end of this lesson, you will be able to:

- Distinguish CORS from authentication, authorization, and CSRF.
- Understand **preflight** requests and the mandatory filter ordering in Security-enabled applications.
- Compare `CorsWebFilter`, Spring WebFlux CORS configuration (`WebFluxConfigurer`, `@CrossOrigin`), and `ServerHttpSecurity.cors(...)`.
- Use one consistent Reactive `CorsConfigurationSource` without accidentally registering multiple CORS filters.
- Troubleshoot issues caused by cookies, origins, headers, methods, multiple security chains, or reverse proxies/gateways.
- Write a working example on **Java 17+, Spring Boot 3.x, Spring Security 6.x**, along with `WebTestClient` tests.

> **Scope:** Spring **WebFlux Reactive**, not Spring MVC/Servlet. Key imports to remember are `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`, `org.springframework.web.cors.reactive.CorsWebFilter`, `ServerHttpSecurity`, and `SecurityWebFilterChain`. Do not copy Servlet APIs such as `HttpSecurity`, `CorsFilter` in `org.springframework.web.filter`, or `org.springframework.web.cors.UrlBasedCorsConfigurationSource` (without `.reactive`) into WebFlux.

## 2. Origin, Preflight, and Actual Requests

An **origin** consists of *scheme + host + port*, excluding the path:

```text
http://localhost:3000         (frontend A)
http://localhost:8080         (backend: different origin)
http://localhost:4200         (frontend B: different origin)
https://localhost:3000        (different scheme)
https://app.example.com       (production origin)
```

Hence `http://localhost:3000/app` and `http://localhost:3000/admin` share the **same origin**, whereas `https://app.example.com` and `https://www.app.example.com` are different origins.

CORS (**Cross-Origin Resource Sharing**) is the contract checked by the browser before allowing JavaScript to read/use a cross-origin response. The server may return:

- `Access-Control-Allow-Origin`: permitted origin.
- `Access-Control-Allow-Methods`: methods allowed during preflight.
- `Access-Control-Allow-Headers`: permitted request headers.
- `Access-Control-Allow-Credentials`: used for requests carrying credentials per Fetch mode.
- `Access-Control-Expose-Headers`: additional response headers JavaScript may read.
- `Access-Control-Max-Age`: duration for which the browser may cache preflight results.
- `Vary`: enables proxies/caches to distinguish responses by origin and relevant preflight metadata.

**CORS does not verify identity.** An allowed origin still needs a password, session, or bearer token if the endpoint is protected. `curl`, service-to-service clients, and Postman do not enforce browser CORS policies; a `curl` command reading the body **does not prove** a frontend website can read it.

### Requests Carrying an Authorization Header Usually Trigger Preflight

When the frontend wants to call:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Authorization: Basic ...
```

the browser normally sends a preflight check first:

```http
OPTIONS /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

This `OPTIONS` request **does not carry the actual request's cookies/credentials in a way the server can use to demand login**. If Security enforces authentication before CORS runs, the request can receive `401 Unauthorized`, `WWW-Authenticate`, or a redirect to login; the browser blocks immediately and the actual GET never happens.

A successful preflight may return:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
```

This is a logical example; Spring may emit headers in a different order or casing, or add `Vary: Access-Control-Request-Method` and `Vary: Access-Control-Request-Headers`. Tests should check **contract values**, not rigid serialization ordering.

**Core principle:** CORS must be evaluated **before Spring Security authentication/authorization** for preflights. The official Spring Security Reactive documentation recommends a `CorsWebFilter` mechanism at the proper order.

## 3. Where CORS Can Be Configured in a WebFlux Application

| Mechanism | Where does it operate? | Best suited when | Key caveats |
| --- | --- | --- | --- |
| `WebFluxConfigurer#addCorsMappings` | WebFlux `HandlerMapping` | Route/controller-level CORS rules | An earlier security WebFilter can block preflight before `HandlerMapping` runs |
| `@CrossOrigin` | Handler/controller | Local cross-origin allowances | Can **combine additively** with global `HandlerMapping` config, widening origins |
| `CorsWebFilter` bean | Top-level WebFlux `WebFilter` | Early CORS needed, including functional endpoints | Must be ordered ahead of security without adding duplicate CORS filters |
| `ServerHttpSecurity.cors(...)` | Inside the security filter chain | WebFlux apps with Spring Security | Uses Reactive `CorsConfigurationSource`; avoid overlapping policy with top-level filter |
| API Gateway / ingress / CDN | Ahead of the service | Centralized policy across multiple services | Both gateway and backend setting headers can break responses |

There is no rule that "everything except X is forbidden". **Avoiding conflicts** means selecting one primary owner for each request path's policy, knowing where preflight is handled, and eliminating contradictory rules.

### `WebFluxConfigurer` and `@CrossOrigin`: Configurations Can Merge

Spring WebFlux supports CORS at `HandlerMapping`; a `@CrossOrigin` on a controller can be **merged** with global mappings. Multi-valued fields like origins, methods, and headers generally merge additively, while single-valued fields like `allowCredentials` and `maxAge` follow override rules.

For example, if global config permits `https://portal.example.com` and one controller has `@CrossOrigin(origins="https://preview.example.com")`, do not assume only preview is allowed: after merging, **both** origins may be allowed on that controller.

This differs from having **two CORS WebFilters** at different positions. With two filters, the earlier filter may block the request or complete the preflight, leaving the second filter no chance to apply its policy. There is no guarantee that "both always write two headers"; the outcome depends on filter ordering and matchers. That ordering dependency makes debugging hard.

### What Does `ServerHttpSecurity.CorsSpec` Do?

Spring Security 6.x supports:

```java
.cors(cors -> cors.configurationSource(source))
```

where `source` is an `org.springframework.web.cors.reactive.CorsConfigurationSource`. Per the Spring Security 6.5 Javadoc, this integrates CORS at the right order; without a source, no allowed-origin list is generated automatically. A matching `CorsConfigurationSource` bean can be discovered automatically; passing it explicitly via `configurationSource(...)` makes the wiring easier to follow.

Conversely:

```java
.cors(cors -> cors.disable())
```

means **do not enable CORS integration inside the security chain**, not a command that alters browser rules. It is appropriate only when CORS already has another clearly designated owner (such as a standalone `CorsWebFilter` ahead of security) or when the product deliberately requires no cross-origin support.

## 4. Typical Conflicts

### 4.1. Registering Both a Standalone CORS Filter and Security CORS

Suppose a system defines a `CorsWebFilter` bean with origins A while Security wires a `CorsConfigurationSource` with origins B:

```java
// Illustrates a conflicting setup; DO NOT use in the main demo:
@Bean
CorsWebFilter corsWebFilter(CorsConfigurationSource sourceA) {
    return new CorsWebFilter(sourceA);
}

// In another security chain:
http.cors(cors -> cors.configurationSource(sourceB));
```

**Problem:** the same request is subject to two policies, and whichever filter runs first may complete preflight or write headers before the other filter runs. There is no longer a single source of truth.

**Fix:** pick **a shared source inside Security CORS alone** *or* a properly ordered top-level `CorsWebFilter` with Security CORS disabled—and remove conflicting `HandlerMapping` rules.

### 4.2. OPTIONS Preflight Returns 401 or Redirects

`OPTIONS` in a CORS preflight normally lacks credentials, yet `.anyExchange().authenticated()` demands login if CORS has not run yet. Adding:

```java
.pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
```

may prevent some 401s yet **does not emit `Access-Control-Allow-Origin`**. This is not a substitute for CORS processing, and an overly broad permit-all may clash with your architecture. Handle preflight early and verify with requests carrying full `Origin` and `Access-Control-Request-*` headers.

### 4.3. Two `Access-Control-Allow-Origin` Headers on the Same Response

Suppose a gateway writes:

```http
Access-Control-Allow-Origin: *
```

while the backend also writes:

```http
Access-Control-Allow-Origin: https://app.example.com
```

The browser reports **multiple values** or an invalid header value. The ACAO header is not a comma-separated list of allowed origins. Designate one layer to emit the header or strip the header added by the overlapping layer; never patch around it by disabling security.

### 4.4. Mismatched Allowed Origin, Method, or Header

An origin includes scheme, host, and port: `http://localhost:3000` differs from `http://localhost:4200`; never add a path or trailing slash in `allowedOrigins`.

A preflight for:

```http
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type,x-csrf-token
```

will be rejected if the policy permits only `GET` or omits `X-CSRF-TOKEN`. Do not set `allowedMethods("*")` and `allowedHeaders("*")` merely to "fix CORS"; stick to the actual frontend contract and paths.

### 4.5. Gateway or Reverse Proxy Intercepting Ahead of the Application

Spring Cloud Gateway, nginx, ingress, or a CDN can answer `OPTIONS` directly or inject ACAO into responses. Tests hitting only the `localhost` service miss errors occurring on the public hostname. Test along the **actual production path**, with clear ownership between gateway and service.

### 4.6. Multiple `SecurityWebFilterChain`s

A source attached to a `/ui/**` chain does not automatically apply to `/api/**` when security matchers differ. An earlier-ordered chain can "swallow" requests before the intended chain sees them. Inspect `securityMatcher`, `@Order`, and the CORS source on every chain rather than merely checking that `.cors(...)` appears somewhere in the codebase.

## 5. Primary Approach: One Reactive `CorsConfigurationSource` Used in Security

This is the configuration chosen for our example: **no separate `CorsWebFilter` bean, no `WebFluxConfigurer` CORS mapping, no `@CrossOrigin` on controllers**. A single configuration source is wired by Spring Security at the proper filter order.

Design:

- Permitted frontend: `http://localhost:3000`.
- Backend: `http://localhost:8080`.
- Cross-origin CORS enabled only on `/api/**`.
- Allowed methods for `/api/**`: `GET`, `OPTIONS`.
- Allowed request headers: `Authorization`, `Content-Type`.
- `allowCredentials(false)` because the demo uses no cross-origin cookies; a later section shows a separate cookie configuration.
- `GET /api/me` requires HTTP Basic; `GET /public/ping` is a public endpoint outside the CORS mapping.

Because the demo calls only `GET`/`OPTIONS`, Spring Security's default CSRF **does not need to be disabled**. State-changing `POST` endpoints must enforce an appropriate CSRF policy independent of CORS.

## 6. Runnable Java 17+ Example

Requires Spring Boot 3.x / Spring Security 6.x / Java 17+ and a Gradle wrapper.

### 6.1. Dependencies (`build.gradle`)

In a project already configured with the Spring Boot plugin and repositories:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Do not add `spring-boot-starter-web`, so the demo does not switch to MVC/Servlet.

### 6.2. File `src/main/java/demo/cors/CorsDemoApplication.java`

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

### 6.3. File `src/main/java/demo/cors/SecurityConfig.java`

```java
package demo.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:3000"));
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    ReactiveUserDetailsService userDetailsService() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo123"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(reader);
    }
}
```

**Explanation:**

1. `UrlBasedCorsConfigurationSource` comes from `org.springframework.web.cors.reactive`, **not the Servlet package**.
2. The source registers only `/api/**`. `GET /public/ping` remains public under security authorization, yet does not receive cross-origin ACAO headers automatically.
3. `.cors(cors -> cors.configurationSource(corsSource))` places CORS **into the security chain at the proper order**. No extra `CorsWebFilter` bean is needed.
4. `.anyExchange().authenticated()` still protects `/api/me` on **actual requests**. Having CORS process `OPTIONS` preflight grants zero permissions for the subsequent `GET`.
5. HTTP Basic is strictly for local demos. **Base64 does not encrypt passwords**; production requires TLS and a suitable authentication mechanism. Never place `reader/demo123` inside a JavaScript bundle.
6. `setAllowCredentials(false)` fits demos that do not rely on cross-origin cookies. It neither replaces authentication/authorization nor means "the browser cannot send any `Authorization` header"; requests with custom headers must still satisfy browser Fetch/CORS policy.
7. Do not call `.csrf(csrf -> csrf.disable())`. CORS and CSRF are independent policies; applications where browsers attach Basic credentials automatically may still need CSRF on write requests.

### 6.4. File `src/main/java/demo/cors/ApiController.java`

```java
package demo.cors;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "user", context.getAuthentication().getName()));
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
```

The controller uses `ReactiveSecurityContextHolder` to obtain the identity verified by Spring Security rather than trusting a username from a query parameter. A successful `GET /api/me` returns:

```json
{"user":"reader"}
```

### 6.5. Running the Application

From the project directory with Gradle wrapper:

```bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
```

Spring Boot's default port in the demo is `8080`. In real production deployments, enable HTTPS, limit details in errors/logs, and remove demo accounts.

## 7. Verifying CORS with curl

### 7.1. Valid-Origin OPTIONS Preflight Without Credentials

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Expected outcome:

- Preflight is accepted, typically `200 OK`, without needing a Basic header.
- `Access-Control-Allow-Origin: http://localhost:3000`.
- Allowed methods include `GET`; allowed headers include `authorization`.
- No `401` challenge or login redirect on `OPTIONS`.

### 7.2. Actual GET with Valid Credentials

```bash
curl -i -u reader:demo123 \
  -H "Origin: http://localhost:3000" \
  http://localhost:8080/api/me
```

Outcome: status `200 OK`, JSON `{"user":"reader"}`, and the frontend's ACAO. `curl -u` sends a Basic header **for local testing only**; never send passwords over plain HTTP in production.

### 7.3. Preflight from a Disallowed Origin

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

With `CorsWebFilter` / default `DefaultCorsProcessor`, disallowed preflights typically return `403 Forbidden`. The key point is not just the status: that origin **is never granted** ACAO allowing a browser to read the API.

### 7.4. Request Without `Origin`

```bash
curl -i -u reader:demo123 \
  http://localhost:8080/api/me
```

Because this is not a CORS request, the server returns JSON `200` **without** ACAO. Omitting CORS headers on requests lacking `Origin` is normal.

### 7.5. Public Endpoint Outside the CORS Mapping

```bash
curl -i \
  -H "Origin: http://localhost:3000" \
  http://localhost:8080/public/ping
```

The endpoint returns `pong` thanks to `.pathMatchers("/public/**").permitAll()`, yet a browser frontend **cannot automatically read** the cross-origin response because `/public/**` is absent from the CORS source. `permitAll` does not configure CORS.

**Note:** `curl` does not enforce browser CORS policies; it only reveals headers and status codes. Always test afterward from a real frontend origin in Developer Tools → Network and inspect both `OPTIONS` and the actual request.

## 8. Integration Testing with `WebTestClient`

File `src/test/java/demo/cors/CorsIntegrationTest.java`:

```java
package demo.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class CorsIntegrationTest {

    private static final String FRONTEND = "http://localhost:3000";
    private static final String REJECTED = "https://evil.example";

    @Autowired
    WebTestClient client;

    @Test
    void preflightDoesNotNeedAuthentication() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectHeader().doesNotExist(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void actualRequestStillNeedsAuthentication() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND);
    }

    @Test
    void allowedOriginAndCorrectPasswordCanGetUser() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectBody()
            .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void disallowedPreflightIsRejected() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, REJECTED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void requestWithoutOriginDoesNotNeedCorsHeaders() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
```

Run:

```bash
# Linux/macOS
./gradlew test --tests 'demo.cors.CorsIntegrationTest'

# Windows
gradlew.bat test --tests "demo.cors.CorsIntegrationTest"
```

**What the tests verify:**

- `preflightDoesNotNeedAuthentication`: CORS runs early enough that `OPTIONS` is not challenged by the Basic filter for credentials.
- `actualRequestStillNeedsAuthentication`: passing preflight **does not** grant access to the API.
- `allowedOriginAndCorrectPasswordCanGetUser`: actual GET with a valid origin and right credentials is permitted to read.
- `disallowedPreflightIsRejected`: policy genuinely rejects untrusted origins.
- `requestWithoutOriginDoesNotNeedCorsHeaders`: same-origin-style or server-to-server requests do not depend on ACAO.

These tests run against a mock WebFlux server; they do not verify browser cookie/third-party policies or gateways. For production, add tests hitting the public hostname through ingress to catch header conflicts outside the app.

## 9. Alternative A: Top-Level `CorsWebFilter`

A standalone `CorsWebFilter` suits applications with functional routes, early filter requirements, or architectures placing filters at the WebFlux layer. **Do not enable it alongside the Security CORS configuration from section 6.**

**Alternative** bean example (snippet inside a `@Configuration`):

```java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
CorsWebFilter standaloneCorsWebFilter() {
    CorsConfiguration cfg = new CorsConfiguration();
    cfg.setAllowedOrigins(List.of("http://localhost:3000"));
    cfg.setAllowedMethods(List.of("GET", "OPTIONS"));
    cfg.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cfg);
    return new CorsWebFilter(source);
}
```

Additional imports:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

In the **alternative security chain**, do not wire a second CORS source filter:

```java
// Only when a top-level CorsWebFilter is registered and runs before Security.
return http
    .cors(cors -> cors.disable())
    .authorizeExchange(ex -> ex
        .pathMatchers("/public/**").permitAll()
        .anyExchange().authenticated())
    .httpBasic(Customizer.withDefaults())
    .formLogin(form -> form.disable())
    .build();
```

`@Order(Ordered.HIGHEST_PRECEDENCE)` declares an intent to run early, yet in systems with multiple WebFilters or gateways you must verify the **actual** execution order. Disabling `ServerHttpSecurity.cors` in this approach **does not turn off browser CORS rules**; responsibility has simply shifted to the top-level `CorsWebFilter`.

Never copy both the primary and alternative approaches into the same project expecting Spring to pick a sensible policy automatically.

## 10. Alternative B: `WebFluxConfigurer` and `@CrossOrigin`

Spring Framework supports **global `HandlerMapping`** configuration as follows:

```java
@Configuration
class WebFluxCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:3000")
            .allowedMethods("GET", "OPTIONS")
            .allowedHeaders("Authorization", "Content-Type")
            .maxAge(1800);
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
```

**This is an alternative to learn from**; do not add it alongside the Security CORS source in section 6. When using only `HandlerMapping` config, if a Security WebFilter requires authentication **before `HandlerMapping`**, preflight still fails with 401; hence Spring Security recommends processing CORS ahead of security. Do not promote `WebFluxConfigurer` alone as the standard fix for every app using Spring Security.

Placing `@CrossOrigin` on a controller:

```java
@CrossOrigin(origins = "https://preview.example.com")
@GetMapping("/api/preview")
public Mono<String> preview() {
    return Mono.just("preview");
}
```

This is an **illustrative snippet inside a controller**, not a standalone Java class. Global + local `HandlerMapping` CORS can combine additively; never assume a local origin replaces all global origins.

If a specific endpoint truly needs its own origin, add a path-specific mapping to the `CorsConfigurationSource` used by security instead of scattering CORS declarations across teams.

## 11. Multiple Security Chains and CORS Sources

A single WebFlux application might have:

- `/api/**` using bearer/JWT or Basic and needing CORS from an SPA.
- `/admin/**` using cookie sessions, intended for only one trusted origin.
- `/public/**` genuinely public, yet not necessarily open cross-origin.

Use `securityMatcher` and `@Order` when defining multiple `SecurityWebFilterChain`s. An illustrative chain configuration snippet:

```java
// Snippet inside @Configuration, with apiCorsSource supplied.
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .cors(cors -> cors.configurationSource(apiCorsSource))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .build();
}
```

Imports for deployment:

```java
import org.springframework.core.annotation.Order;
import org.springframework.security.web.server.util.matcher
    .PathPatternParserServerWebExchangeMatcher;
```

This is **not a standalone runnable class**; `apiCorsSource` and the concrete authentication mechanism must be provided by the application, and remaining chains must be configured per their policies. Goal: show that CORS must live in the **chain that actually matches the request**, not arbitrarily on just any chain.

**Questions you must test:**

1. Does `OPTIONS /api/me` match the API security chain in the right order?
2. Is `/api/**` allowed for origin A without accidentally opening `/admin/**` to A?
3. Does a top-level `CorsWebFilter` bean override per-chain policies?
4. Does a fallback chain precede the API chain, preventing the API chain from ever matching?
5. When using cookies/sessions on another chain, do its CORS credentials and CSRF align with that chain's policy?

## 12. Credentials, Cookies, JWTs, and CORS

`setAllowCredentials(true)` is appropriate only when the frontend needs **credentialed cross-origin responses** (such as Fetch `credentials: "include"` with cookies). Accompanying rules:

- Permit only **exact trusted origins**; never use `allowedOrigins("*")` with credentials. Spring Framework validates this rule.
- Set `Access-Control-Allow-Credentials` per policy, yet **never assume this header forces the browser to send cookies**: cookies are still governed by `Secure`, `SameSite`, domain/path, third-party policies, and Fetch credentials mode.
- When using session cookies on `POST`/`PUT`/`DELETE`, require valid CSRF tokens if your threat model demands it. CORS does not stop all browser-submitted form requests.
- If the frontend sends `X-CSRF-TOKEN`, declare that header in `allowedHeaders`, alongside `allowedMethods` for the actual request.
- For bearer tokens sent explicitly by the frontend in `Authorization`, permit `Authorization` through preflight and still validate token/issuer/audience/scope on the backend.
- Never turn on wildcard origins or abuse `allowedOriginPatterns("*")` with credentials just because a dev frontend runs on multiple ports.

An **alternative** illustrative config for a cookie-based frontend:

```java
CorsConfiguration cookieCors = new CorsConfiguration();
cookieCors.setAllowedOrigins(List.of("https://app.example.com"));
cookieCors.setAllowCredentials(true);
cookieCors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cookieCors.setAllowedHeaders(List.of(
    "Content-Type", "X-CSRF-TOKEN"));
cookieCors.setMaxAge(600L);
```

This is solely the CORS configuration slice for another security model, without implementing session login or the CSRF repository. On a cookie-session frontend, `fetch` might use:

```javascript
fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
```

The request can still be blocked by the browser if cookie policies disallow sending, or return 401 from the API if no session exists. Never fix this with a wildcard origin.

## 13. CORS Does Not Replace CSRF, Authentication, or Authorization

Three scenarios to distinguish:

**Scenario A:** `OPTIONS` preflight returns `200`, while actual `GET` returns `401` due to missing Basic/JWT. This can be the **intended behavior**: the frontend origin is allowed to call the API, yet the request is unauthenticated.

**Scenario B:** `OPTIONS` for `POST` succeeds, while actual `POST` returns `403` due to a missing CSRF token. This can be **CSRF protection working properly**, not missing CORS headers. When browsers auto-attach cookies, never disable CSRF just to make the `POST` succeed.

**Scenario C:** `GET` has valid credentials yet returns `403` due to insufficient role/scope. CORS governs only the origin, not whether the user is permitted to read the resource.

Therefore, the proper pipeline is: **preflight policy → actual request → authentication → CSRF/authorization/business policy**. Each step can reject independently and should be monitored separately.

CORS protects only browser interactions. Non-CORS clients such as `curl` can still call the API; the backend must authenticate and authorize every request itself. Never substitute CORS for API keys, OAuth2 scopes, or object ownership checks.

## 14. Gateways/CDNs and the "Works on Localhost, Fails in Production" Symptom

When the request path is:

```text
Browser → CDN / Ingress / Gateway → WebFlux / Spring Security → Handler
```

CORS can be handled at the proxy layer ahead of the backend. Gateways sometimes **answer `OPTIONS` directly** or **inject ACAO onto responses** after the backend. If the backend also sets ACAO and the two policies differ, the browser sees multiple values and rejects the response.

**Standardization steps:**

1. Identify which component truly receives preflight first and which emits `Access-Control-Allow-*` on the public hostname.
2. Assign one owner of the CORS policy per route: the gateway **or** the application (or a clearly contracted division).
3. If the gateway sets headers, keep the app from emitting incompatible duplicates; if the app owns CORS, keep the gateway from overwriting it arbitrarily.
4. Test both `OPTIONS` and actual requests through the **public URL**, not only the localhost service.
5. Verify `Vary: Origin` and preflight headers so caches/proxies never serve origin A's policy to origin B.
6. Check gateway-generated error responses (`502`, `503`): the browser console may print "CORS error" solely because the error response lacks ACAO, while the root cause is an upstream outage.
7. Never log raw `Authorization`/JWT/cookie/CSRF values in telemetry while debugging.

Never add `Access-Control-Allow-Origin: *` in production as a quick fix; that changes which frontends are permitted to read data.

## 15. Symptom-Based Diagnosis

| Symptom | Possibility | What to check |
| --- | --- | --- |
| Preflight `OPTIONS` `401` | Security runs before CORS or source is on wrong chain | Send `OPTIONS` with full headers; check matchers and filter order |
| `OPTIONS` redirects to `/login` | Form login entry point intercepts preflight | CORS filter must run before authentication |
| `OPTIONS` `403` | Origin/method/request header disallowed | Compare `Origin`, `Access-Control-Request-*`, and source |
| `OPTIONS` `200`, `GET` `401` | Actual request authentication missing/invalid | Check presence of `Authorization`/Cookie without logging values |
| `OPTIONS` `200`, `POST` `403` | CSRF or authorization, not necessarily CORS | Check token, roles, and CORS headers |
| Browser reports multiple ACAO | Both gateway and app, or two filters, set the header | Inspect raw response headers at each hop |
| Browser reports wildcard with credentials | `*` and `allowCredentials(true)` are incompatible | Use trusted explicit origins |
| Curl `GET` `200` yet frontend gets CORS error | Curl does not enforce CORS like a browser | Browser Network/Console, preflight, and ACAO |
| `@CrossOrigin` does not fix `OPTIONS` | Security blocks preflight ahead of `HandlerMapping` | Run CORS before security, not only annotations |
| Public `GET` blocked by browser | `permitAll` does not configure CORS | Check CORS source path mappings |
| 500 error response lacks ACAO | Error handler/proxy omits CORS headers | Fix root error and error-handling filter order |
| Only one frontend origin works | Port/scheme/host differs from allowed origins | Compare exact origin in Network tab |
| Session cookie not sent | Fetch mode/SameSite/Secure/third-party cookie policy | Check cookie attributes and browser policies |
| Tests fail after version upgrade | Auto-config/source/chain behavior changed | Check release notes and integration tests |

**Sequential debugging workflow:**

1. Record the frontend origin + API URL + method + expected request headers.
2. Reproduce the exact preflight with `Origin` and `Access-Control-Request-Method` using `curl`/`WebTestClient`.
3. Inspect preflight headers/status first, then the actual request.
4. Inventory all places declaring policy: `@CrossOrigin`, `WebFluxConfigurer`, `CorsWebFilter`, `ServerHttpSecurity.cors`, gateway/proxy.
5. Choose **one CORS owner** and remove unintended duplicate configs; confirm the source is **Reactive**.
6. Check security chain matchers/order, cookies/CSRF, and authorization separately.
7. Re-run positive and negative integration tests, then verify in a real browser and through the gateway.

Temporary development logging may be enabled if helpful:

```properties
logging.level.org.springframework.security=DEBUG
```

Never log tokens, Basic passwords, raw `Authorization`, cookies, or session IDs. A CORS error is never a reason to drop a security chain or enable wildcards across an entire API.

## 16. Myths to Avoid

**Myth 1: `permitAll()` solves CORS.** No. It only waives authorization for matching routes and never emits `Access-Control-Allow-Origin`.

**Myth 2: `@CrossOrigin` always runs before security.** No. `@CrossOrigin` runs in `HandlerMapping`; security WebFilters can reject requests before reaching it.

**Myth 3: Adding more `CorsWebFilter`s is safer.** No. Multiple filters/policies can process the same request with order-dependent results.

**Myth 4: Returning status 200 on `OPTIONS` is enough.** No. Browsers also validate allow-origin, allow-methods, allow-headers, and credentials policies.

**Myth 5: Having ACAO means the user is authenticated.** No. CORS only governs whether the browser lets JS use a cross-origin response.

**Myth 6: CORS stops CSRF.** No. Cross-site forms can still be submitted by browsers; cookie-based unsafe methods need proper CSRF protection.

**Myth 7: `*` works with all credentialed requests.** No. `allowCredentials(true)` and wildcard `allowedOrigins("*")` are invalid under standard CORS rules.

**Myth 8: Same host means same origin regardless of port.** No. Port and scheme are part of the origin.

**Myth 9: A successful curl POST means the browser will succeed.** No. Curl does not enforce browser CORS policies; always test the real frontend.

**Myth 10: Only the backend matters; gateways are unrelated.** No. Proxies can inject or overwrite CORS headers; inspect the full path.

**Myth 11: CORS on one `SecurityWebFilterChain` automatically covers the rest.** Never assume that; it depends on matchers and filter placement.

**Myth 12: When hitting errors, simply disable CORS in Security without replacing it.** Without a properly ordered replacement filter/policy, cross-origin frontends remain unsupported.

## 17. Pre-Production Checklist

| Item | Passing criteria |
| --- | --- |
| Proper WebFlux APIs | Reactive `CorsConfigurationSource`, `UrlBasedCorsConfigurationSource`, `ServerHttpSecurity` |
| CORS owner | Clear ownership assigned to Security, standalone filter, `HandlerMapping`, or gateway |
| No overlapping policies | No conflicting origins/methods/headers on the same path |
| Filter ordering | `OPTIONS` preflight handled before authentication checks |
| Positive origin | Allowed origins receive exact ACAO and allowed methods/headers |
| Negative origin | Unknown origins rejected, never accidentally reflected |
| Security | Actual requests still enforce proper authentication and authorization |
| CSRF | CSRF never disabled out of confusion with CORS errors |
| Exact origins | Proper scheme/host/port; no paths or trailing slashes |
| Credentialed requests | Explicit trusted origins, proper `allowCredentials`, cookie/Fetch mode |
| Gateway | No duplicate ACAO; tested through public hostname |
| Multiple chains | Matchers and CORS sources wired to the right chains |
| Errors | 401/403/5xx carry appropriate headers when the frontend needs to read errors |
| Caching | Proper `Vary` and private response cache policies |
| Browser | Network tab confirms both `OPTIONS` and actual request |
| Observability | Causes logged safely without leaking credentials |
| Tests | `WebTestClient` and browser E2E include allow/deny cases |

## 18. Self-Check Questions

**1. Why must preflight run before Spring Security?** Because `OPTIONS` typically carries no credentials for the server to authenticate like an actual request; running Security first rejects it with 401 or a redirect.

**2. Do `@CrossOrigin` and WebFlux global mappings always produce duplicate headers?** No. They have merge rules at `HandlerMapping`; the risk is origins merging and widening unintentionally.

**3. Why shouldn't you register both a standalone `CorsWebFilter` and `.cors(configurationSource(...))` with different rules?** Requests can be intercepted/completed by the earlier filter or receive conflicting CORS headers, making the effective policy hard to predict.

**4. Is `OPTIONS permitAll` sufficient?** No. It neither generates CORS headers nor validates requested methods/headers.

**5. What happens if `GET /api/me` has a valid ACAO yet the password is wrong?** The API still returns an authentication failure/401. CORS does not grant authorization.

**6. Can `allowedOrigins("*")` be combined with `allowCredentials(true)`?** No; use trusted explicit origins or tightly designed and thoroughly tested patterns.

**7. Is there a contradiction when `curl` sees 200 yet the browser reports CORS?** No. `curl` does not enforce browser CORS policies.

**8. Is adding CORS only to the UI security chain enough for the API chain?** Never assume so. Verify the exact API chain matcher and source.

**9. Can a gateway cause CORS errors even when the backend is right?** Yes. A gateway can block `OPTIONS` or inject/alter ACAO, causing bad responses on the public hostname.

**10. What is the most critical check when changing a CORS policy?** Ensuring you do not accidentally expose extra origins or weaken authentication/authorization/CSRF; require both positive and negative integration tests.

## Remember

- Spring Security Reactive requires **CORS before authentication** so preflights are not challenged.
- `CorsWebFilter`, `WebFluxConfigurer`, `@CrossOrigin`, and `ServerHttpSecurity.cors(...)` operate at different scopes and stages.
- For WebFlux + Security, **one Reactive `CorsConfigurationSource` passed to `.cors(cors -> cors.configurationSource(...))`** is clear and testable.
- Never stack conflicting CORS filters; distinguish `HandlerMapping` merging from two independent `WebFilter`s.
- `allowCredentials`, origins, methods, request headers, gateways, and cookie policies all affect browser behavior.
- CORS **does not replace authentication, authorization, or CSRF**. A passing preflight never guarantees the actual request succeeds.
- Test both **`OPTIONS` and actual requests**, **allowed and forbidden origins**, **with and without authentication**, and the full path through any **gateway**.

### Official References

- [Spring Security 6.5 — Reactive CORS integration](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — `ServerHttpSecurity.CorsSpec`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html)
- [Spring Security 6.5 — `ServerHttpSecurity` Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Framework 6.2 — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — `CorsWebFilter` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html)
- [Spring Framework 6.2 — `CorsConfiguration` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
