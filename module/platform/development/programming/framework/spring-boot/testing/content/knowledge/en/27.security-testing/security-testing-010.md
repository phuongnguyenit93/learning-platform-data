# Testing CORS, Security Headers, and Security Error Handling in Spring Boot

## Objectives and scope

A REST API built with Spring Boot and Spring Security can return `200 OK` with the right payload and still harbor security or integration bugs: browsers fail to send requests because **CORS preflight is blocked**, endpoints accidentally respond to disallowed origins, pages can be embedded in iframes, security headers are missing, error responses leak internal details, or `401`/`403` get conflated.

This lesson belongs to the **Security** branch of the **Spring Boot – testing** module, focusing on **Testing CORS, security headers, and security error handling**. The emphasis is writing **security integration tests with concrete assertions** to catch mismatches between `SecurityFilterChain` configuration, MVC controllers, and actual HTTP responses.

After completing it, you will be able to:

1. Distinguish **CORS**, **authentication**, **authorization**, and **CSRF**, instead of treating them as one mechanism.
2. Explain why **CORS preflight `OPTIONS`** must be handled before authentication and why it typically carries no session cookie or `Authorization` header.
3. Build a `CorsConfigurationSource` restricting **origin/method/request headers** and assert `Access-Control-Allow-Origin`, `Allow-Credentials`, `Allow-Methods`, `Allow-Headers`, `Expose-Headers`, and `Max-Age`.
4. Write **allow** and **deny** cases: unknown origin, disallowed method, disallowed request header, and cross-origin GET with/without authentication.
5. Verify response headers `X-Content-Type-Options`, `X-Frame-Options`, `Cache-Control`, `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy`, and `Permissions-Policy`.
6. Know which headers are Spring Security 6.3 defaults, which require explicit opt-in, and why HSTS appears only over HTTPS.
7. Write tests distinguishing **401 unauthenticated**, **403 authenticated yet unauthorized**, **403 missing/invalid CSRF**, and **400 invalid request data**.
8. Distinguish `AuthenticationEntryPoint`/`AccessDeniedHandler` inside the **security filter chain** from `@RestControllerAdvice` handling errors inside MVC.
9. Keep JSON error responses safe and consistent, never exposing stack traces, credentials, or internal details.
10. Test with `@SpringBootTest` + `@AutoConfigureMockMvc` + `spring-security-test`, keeping security filters active instead of disabling them for green tests.
11. Analyze MockMvc limitations regarding **TLS, reverse proxies, browser CORS enforcement, HTTP/2, and end-to-end networking**.
12. Run the **Java 17 + Spring Boot 3.3.5 + Spring Security 6.3.x + Gradle + JUnit Jupiter** example project with no Docker or database required.

**Core principle:** **CORS does not replace authorization.** An allowed origin does not automatically grant read or write permissions; non-browser clients can still call the API outside browser CORS policy. Security tests must verify every defense layer and error path separately.

## 1. Security architecture of a request

Spring MVC/Spring Security is built from servlet filters, interceptors, and controllers. A request typically flows through:

~~~text
Browser or HTTP client
         |
         v
HTTP request: Method / Origin / Authorization /
              Cookies / CSRF / Content-Type
         |
         v
Servlet container / reverse proxy boundary
         |
         v
Spring Security FilterChainProxy
         |
         +-- CORS processing
         |     +-- Valid preflight: returns OPTIONS response early
         |     +-- Forbidden origin/method/header: rejects CORS
         |
         +-- Security headers / CSRF / Authentication
         |
         +-- Authorization
         |     +-- Not logged in / wrong credentials -> 401
         |     +-- Logged in yet lacking permission -> 403
         |
         v
DispatcherServlet -> @RestController
         |
         +-- @Valid / JSON binding -> 400 when invalid
         |
         +-- @RestControllerAdvice (MVC exceptions)
         |
         v
HTTP response: status + headers + JSON body
~~~

The diagram shows **conceptual** ordering, not a rigid enumeration of every filter or custom chain. Security exceptions can be handled **before reaching the controller**, so `@ControllerAdvice` is not the sole place coordinating security errors.

### Four axes requiring separate tests

| Axis | Question to answer | Evidence |
| --- | --- | --- |
| CORS | Which browser origins may read API responses? | `OPTIONS`/`Origin`/`Access-Control` response headers |
| Authentication | Who authenticated? | 401 when missing/wrong credentials, 200 when valid |
| Authorization | Which actions may that identity perform? | 403 for wrong role, 200/201 for right role |
| CSRF | Does a state-changing request carry a valid token? | POST missing/wrong token 403; valid token proceeds |

For instance, a `POST /api/orders` can be blocked right at CORS for an invalid origin, at CSRF for a missing token, at authentication for not logging in, or at authorization for a read-only role. **Not every 403 shares the same cause.**

## 2. CORS is not authentication

**Cross-Origin Resource Sharing (CORS)** is a browser security model mechanism allowing servers to declare which **web origins** may read responses from cross-origin requests. An origin is the tuple **scheme + hostname + port**.

Examples:

- `https://portal.example.test` is one origin.
- `https://portal.example.test:8443` is a different origin because the port differs.
- `http://portal.example.test` differs because the scheme differs.
- `https://evil.example.test` is not allowed merely for sharing the `example.test` suffix.
- `Origin: null` carries special semantics (sandbox/file/opaque origins) and must not be automatically trusted.

### What does CORS restrict?

Browsers enforce CORS when JavaScript on one origin attempts to read responses from another origin. CORS does not prevent requests from being sent in all cases (simple requests can still be dispatched), and it **is not a firewall** or authorization check against curl, Postman, or server-to-server callers. Non-browser HTTP clients can forge or omit the `Origin` header at will; the server must still authenticate and authorize every call.

**Wrong:** “Allowing the frontend origin makes the endpoint secure.”

**Right:** “Allowing the frontend origin lets browsers access it cross-origin per policy; the endpoint must still validate tokens/sessions/roles and request inputs.”

### What is preflight?

For requests that are not “simple” under Fetch/CORS rules, browsers typically send an **`OPTIONS` preflight** before the real request. Suppose a frontend wants to send:

~~~http
POST /api/orders HTTP/1.1
Origin: https://portal.example.test
Authorization: Basic ...
Content-Type: application/json
X-Request-Id: req-123

{"item":"book","quantity":2}
~~~

The browser may send preflight first:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-request-id
~~~

If the server approves, a representative response looks like:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type,x-request-id
Access-Control-Max-Age: 600
~~~

This is an **illustrative response example**, not fixed stdout/body across every servlet container. Method/header lists and whitespace formatting can vary by CORS processor. Tests should verify meaningful semantics rather than brittle non-contract formatting.

### Why does preflight usually carry no credentials?

Browser preflights normally do not send authorization credentials like the main request. If a security filter enforces login or CSRF before checking CORS, preflight can return 401/403 and trigger browser CORS errors on the frontend. Spring Security recommends **processing CORS before Spring Security authorization** via `http.cors(...)` and `CorsConfigurationSource` or proper MVC CORS integration.

### Allowed vs exposed headers

These work in opposite directions:

- `Access-Control-Allow-Headers`: **request headers** browsers are permitted to send cross-origin, e.g., `Authorization`, `Content-Type`.
- `Access-Control-Expose-Headers`: **response headers** JavaScript is permitted to read beyond CORS-safelisted response headers, e.g., `X-Request-Id`.

Allowing request header `Authorization` does not mean frontend JavaScript can read response header `X-Request-Id`. Test both directions explicitly.

## 3. Safe CORS allowlists

An illustrative configuration using an **exact origin**:

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(
        List.of("https://portal.example.test"));
config.setAllowedMethods(List.of("GET", "POST"));
config.setAllowedHeaders(
        List.of("Authorization", "Content-Type",
                "X-Request-Id"));
config.setExposedHeaders(List.of("X-Request-Id"));
config.setAllowCredentials(true);
config.setMaxAge(600L);
~~~

This snippet belongs to the full configuration class below. When `allowCredentials=true`, **do not configure `allowedOrigins("*")`**. Spring Framework rejects that wildcard/credentials combination. For use cases needing origin patterns, `allowedOriginPatterns` is a separate API that still requires strict allowlist management, never overly broad patterns.

### Never “echo Origin” blindly

Architectural anti-pattern:

~~~java
response.setHeader(
    "Access-Control-Allow-Origin",
    request.getHeader("Origin"));
~~~

Reflecting the origin without validating it allows any arbitrary origin into the header. Some setups also pair it with `Access-Control-Allow-Credentials: true`, exposing credentialed responses to untrusted sites.

A sound allowlist:

1. Lists only origins owned or vetted by the team.
2. Separates production, staging, and local development.
3. Never uses wildcards on credentialed APIs.
4. Restricts methods and headers to actual needs.
5. Includes negative tests with a specific disallowed origin.
6. Never relies on CORS to guard endpoints against non-browser clients.
7. Accounts for `Vary: Origin` and cache/CDN behavior when responses vary by origin.
8. Never assumes “works in local browser tests” equals a sound production policy.

## 4. Security headers: defaults and opt-in

Spring Security includes defaults that mitigate browser risks. Still, **not every common header is enabled by default**.

| Header | Purpose | Testing notes |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Prevents content MIME sniffing | Spring Security default |
| `X-Frame-Options: DENY` | Mitigates clickjacking | Spring Security default |
| `Cache-Control: no-cache, no-store, ...` | Reduces caching of sensitive responses | Default for relevant responses; apps can explicitly override |
| `Pragma: no-cache`, `Expires: 0` | Legacy cache control compatibility | Default unless custom cache policy overrides |
| `Strict-Transport-Security` | Forces browsers to use HTTPS for the host once received | **Added only on HTTPS** by default |
| `X-XSS-Protection: 0` | Disables legacy XSS auditor prone to side effects | Not a replacement for CSP/output encoding |
| `Content-Security-Policy` | Restricts script/style/object/frame sources | **Not present** unless configured |
| `Referrer-Policy` | Controls referrer details sent outbound | **Must be configured** |
| `Permissions-Policy` | Controls camera/microphone/geolocation access… | **Must be configured** |
| `Access-Control-Allow-Origin` | Cross-origin browser read permission | CORS, **not** a standalone default security header |

### HSTS: cannot be verified over plain HTTP

Spring Security adds HSTS only when a request is recognized as **secure/HTTPS**. In MockMvc:

~~~java
mvc.perform(get("/api/public").secure(true))
    .andExpect(header().exists(
            "Strict-Transport-Security"));
~~~

Whereas on a plain request:

~~~java
mvc.perform(get("/api/public"))
    .andExpect(header().doesNotExist(
            "Strict-Transport-Security"));
~~~

These two snippets assume `mvc` is injected and `get`/`header` are statically imported. If the app sits behind TLS-terminating ingress/reverse proxies, the servlet container must be configured to recognize forwarded scheme info; MockMvc `secure(true)` **does not prove** production ingress/proxies detect HTTPS properly.

### CSP is defense-in-depth, not input validation

`Content-Security-Policy` helps browsers restrict executable content sources, yet never replaces output encoding, validation, HTML sanitization, or avoiding unsafe DOM sinks. A JSON-only API can enforce a strict policy; an app serving HTML, inline scripts, or third-party assets must design a tailored policy and verify it in real browsers.

### Headers not to rely on

- Do not use `X-XSS-Protection: 1` as a primary XSS defense; modern browsers retired the legacy filter.
- Do not enable HPKP automatically; it is no longer recommended.
- Never add `Access-Control-Allow-Origin: *` just to silence frontend errors on credentialed endpoints.
- Never strip security headers from error responses. Error responses can also carry sensitive context.
- Never configure a strict CSP solely inside test config when production omits it.

## 5. Authentication vs authorization vs CSRF vs validation errors

| Status | Typical scenario | Expected |
| --- | --- | --- |
| 200/201 | Valid authentication, permission, and request data | Success |
| 401 Unauthorized | Unauthenticated or wrong Basic credentials | Authentication error; include `WWW-Authenticate` for Basic |
| 403 Forbidden | Authenticated yet lacking role/permission | Authorization error |
| 403 Forbidden | Missing/invalid CSRF on unsafe method with CSRF enabled | Blocked by CSRF filter, potentially **before** authentication/authorization |
| 403 Forbidden | CORS preflight disallowed origin/method/header | Rejected by CORS filter; typically **without** custom auth JSON error bodies |
| 400 Bad Request | Input binding/validation error after passing security filters | MVC validation error, handled by `@RestControllerAdvice` |

**Important:** Never write tests assuming “every 403 returns JSON `ACCESS_DENIED`”. A 403 can originate from **`CorsFilter`**, **`CsrfFilter`**, **`AccessDeniedHandler`**, or business logic, each taking different handlers. Clearly isolate each scenario and assert meaningful responses.

### Never leak details in error bodies

For authentication/authorization, safe bodies look like:

~~~json
{"code":"AUTH_REQUIRED"}
~~~

or:

~~~json
{"code":"ACCESS_DENIED"}
~~~

Avoid returning:

~~~json
{"error":"SELECT * FROM users WHERE ...; username=admin; password=..."}
~~~

This is an example of *what never to do*. Never echo stack traces, class names, SQL queries, secrets, auth tokens, internal audit/claims, or details enabling account enumeration.

Internal logs may record request IDs, statuses, sanitized exception types, and causes for investigation, without exposing them verbatim in public JSON bodies.

## 6. Runnable project: Java 17, Spring Boot 3.3.5, Spring Security

The project uses the **Spring MVC servlet stack**, not WebFlux. We will test:

- `/api/public` for everyone (returns JSON and response header `X-Request-Id`).
- `GET /api/orders` for roles `READER` or `EDITOR`.
- `POST /api/orders` for role `EDITOR` only, plus **CSRF token** and input validation.
- Unlisted paths -> `denyAll()`.
- CORS limited to `https://portal.example.test`, `GET`/`POST`, and three specified request headers.
- JSON bodies for authentication/authorization errors via Security handlers; MVC validation errors via `@RestControllerAdvice`.
- Default security headers plus custom CSP/Referrer/Permissions policies.

**This project needs no database, Docker, JWT server, LDAP, email, or partner API.** In-memory accounts and Basic auth exist purely for learning filter behavior; **never take `{noop}` passwords as a recommendation for production**.

### 6.1. Directory tree

~~~text
security-web-test-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/securitylab/
    │   ├── SecurityLabApplication.java
    │   ├── ApiSecurityConfig.java
    │   ├── ShopApiController.java
    │   └── ApiValidationAdvice.java
    └── test/java/com/example/securitylab/
        ├── CorsPolicyTest.java
        ├── SecurityHeaderTest.java
        └── SecurityFailureTest.java
~~~

Gradle Wrapper scripts/JAR are generated with an appropriate Gradle version or copied from a standard repo; `gradle-wrapper.jar` is a binary file and cannot be pasted from Markdown.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'security-web-test-lab'
~~~

### 6.3. `build.gradle` (Groovy DSL)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Explanation:

- `spring-boot-starter-web` brings Spring MVC, embedded Tomcat, Jackson HTTP message converters, and `MockMvc` test infrastructure.
- `spring-boot-starter-security` brings the Spring Security servlet filter chain, Basic authentication, CSRF, and security headers.
- `spring-boot-starter-validation` brings Jakarta Validation `@NotBlank`, `@Min`, and Hibernate Validator.
- `spring-boot-starter-test` brings Spring Boot Test, JUnit Jupiter, MockMvc support, Hamcrest, and assertions.
- `spring-security-test` brings `httpBasic()`, `user()`, and `csrf()` request post-processors.
- `useJUnitPlatform()` tells Gradle to discover JUnit Jupiter tests.
- Spring Security/JUnit/Validation versions are managed by the Boot BOM; never pin Spring Security 7 into a Boot 3.3 project.

**`@WebMvcTest` is omitted from the runnable classes**, because the goal is verifying **the application's real security filter chain configuration**. MVC slices can still work if configs/filters are explicitly imported, though full-context MockMvc clarifies the lesson's boundary.

### 6.4. `SecurityLabApplication.java`

~~~java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
~~~

`@SpringBootApplication` acts as the root component scan; the other three classes sit in the same package so Spring discovers them. Run the project via `./gradlew test`, or `./gradlew bootRun` for manual HTTP smoke tests on the default port.

## 7. `ApiSecurityConfig.java`: CORS, authentication, roles, and headers

**`src/main/java/com/example/securitylab/ApiSecurityConfig.java`**

~~~java
package com.example.securitylab;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiSecurityConfig {

    public static final String ALLOWED_ORIGIN =
            "https://portal.example.test";

    public static final String CSP =
            "default-src 'none'; base-uri 'none'; "
                + "frame-ancestors 'none'";

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(ALLOWED_ORIGIN));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Request-Id"));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    UserDetailsService userDetailsService() {
        // DEMO-ONLY credentials.
        // Never use {noop} in production.
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader-pass")
                .roles("READER")
                .build(),
            User.withUsername("editor")
                .password("{noop}editor-pass")
                .roles("EDITOR")
                .build());
    }

    @Bean
    AuthenticationEntryPoint apiAuthenticationEntryPoint() {
        return (request, response, exception) -> {
            response.setHeader(
                "WWW-Authenticate", "Basic realm=\"demo\"");
            writeError(
                response, HttpServletResponse.SC_UNAUTHORIZED,
                "AUTH_REQUIRED");
        };
    }

    @Bean
    AccessDeniedHandler apiAccessDeniedHandler() {
        return (request, response, exception) ->
            writeError(
                response, HttpServletResponse.SC_FORBIDDEN,
                "ACCESS_DENIED");
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiAuthenticationEntryPoint,
            AccessDeniedHandler apiAccessDeniedHandler)
            throws Exception {

        http
            .cors(Customizer.withDefaults())
            // Keep CSRF enabled to test real behavior.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                        HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(
                        HttpMethod.GET, "/api/orders")
                    .hasAnyRole("READER", "EDITOR")
                .requestMatchers(
                        HttpMethod.POST, "/api/orders")
                    .hasRole("EDITOR")
                .anyRequest()
                    .denyAll())
            .httpBasic(basic -> basic
                .authenticationEntryPoint(
                    apiAuthenticationEntryPoint))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    apiAuthenticationEntryPoint)
                .accessDeniedHandler(
                    apiAccessDeniedHandler))
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(CSP))
                .referrerPolicy(referrer -> referrer
                    .policy(
                        ReferrerPolicyHeaderWriter
                            .ReferrerPolicy.NO_REFERRER))
                .permissionsPolicy(permissions -> permissions
                    .policy(
                        "camera=(), microphone=(), "
                        + "geolocation=()")));

        return http.build();
    }

    private static void writeError(
            HttpServletResponse response,
            int status,
            String code) throws IOException {

        response.setStatus(status);
        response.setCharacterEncoding(
                StandardCharsets.UTF_8.name());
        response.setContentType(
                MediaType.APPLICATION_JSON_VALUE);

        // code is supplied from trusted string constants;
        // never embed exception messages or client input into JSON.
        response.getWriter().write(
                "{\"code\":\"" + code + "\"}");
    }
}
~~~

### 7.1. How does `CorsConfigurationSource` connect to the security chain?

`UrlBasedCorsConfigurationSource` is a bean containing policy for `/api/**`. `http.cors(Customizer.withDefaults())` instructs Spring Security to integrate CORS processing into the security chain. Spring Security picks up the declared `UrlBasedCorsConfigurationSource`, letting preflight run **before** normal login/CSRF requirements.

**Key reminder:** Never declare `OPTIONS /api/orders` as `permitAll` assuming CORS is configured. Without a CORS processor, the server can return 200/403 on OPTIONS while **omitting `Access-Control-Allow-Origin`**, causing browsers to still reject the main request. Conversely, a proper CORS processor must reject origins/methods/headers outside the allowlist.

### 7.2. Why does the origin contain no asterisk?

Because the demo sets `allowCredentials(true)`, the policy uses an exact origin. When browsers send cookies or HTTP credentials under Fetch credentials mode, servers must approve a specific origin; wildcards are incompatible with credentialed responses under browser rules.

**Production practice:** allowed origins should be externalized per environment (configuration properties) using a reviewed allowlist. Constants are used in this tutorial so assertions stay independent of CI settings. Never “fix” a production allowlist by echoing the request `Origin` blindly.

### 7.3. `authorizeHttpRequests` must match HTTP methods

- GET `/api/public` -> `permitAll`, no authentication required.
- GET `/api/orders` -> role `READER` or `EDITOR`.
- POST `/api/orders` -> role `EDITOR`, plus valid CSRF.
- Other paths/methods -> `denyAll`.

`hasRole("EDITOR")` maps to authority `ROLE_EDITOR`. Use `User.withUsername(...).roles("EDITOR")` so Spring applies the prefix cleanly; avoid `hasRole("ROLE_EDITOR")` which causes a double prefix.

### 7.4. Basic authentication and JSON errors

The demo defines two test users. When credentials are missing or wrong:

- `AuthenticationEntryPoint` returns 401.
- The response adds `WWW-Authenticate: Basic realm="demo"`.
- Body is `{"code":"AUTH_REQUIRED"}`.

When authenticated without sufficient permission:

- `AccessDeniedHandler` returns 403.
- Body is `{"code":"ACCESS_DENIED"}`.

Both callbacks **live inside Spring Security's filter handling**. They are configured explicitly, including on the HTTP Basic filter, to prevent default divergences when Basic auth fails. Error bodies contain no exception messages or stack traces.

### 7.5. Why keep CSRF enabled?

In the demo, we intentionally keep default `CSRF` enabled so we can test its effect on the unsafe `POST` method. In a truly stateless API accepting Bearer tokens solely from the `Authorization` header without browser cookies or ambient credentials, a team may decide differently after threat modeling. Never cite “REST API” as the sole excuse to disable CSRF: if the app uses session cookies, browser Basic auth, or cookie-based authentication, CSRF remains a live risk.

### 7.6. Security headers and scope

CSP in the example is `default-src 'none'; base-uri 'none'; frame-ancestors 'none'`. That very strict policy fits a JSON-returning REST API serving no frontend HTML assets. If an app also serves HTML UI, that policy can block needed scripts/styles; tailor CSP per response/site or filter chain rather than copying blindly.

`Referrer-Policy: no-referrer` and `Permissions-Policy: camera=(), microphone=(), geolocation=()` are **opt-in**; Spring Security 6.3 provides the matching DSL. Defaults such as `nosniff`, `X-Frame-Options: DENY`, and cache-control remain active.

## 8. `ShopApiController.java`: real endpoint under test

**`src/main/java/com/example/securitylab/ShopApiController.java`**

~~~java
package com.example.securitylab;

import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ShopApiController {

    @GetMapping("/public")
    public ResponseEntity<Map<String, String>> publicInfo() {
        return ResponseEntity.ok()
            .header("X-Request-Id", "server-generated-demo")
            .body(Map.of("message", "public-ok"));
    }

    @GetMapping("/orders")
    public List<OrderView> listOrders() {
        return List.of(
            new OrderView("ORD-001", "Java book", 1));
    }

    @PostMapping("/orders")
    public ResponseEntity<OrderView> createOrder(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderView created = new OrderView(
                "ORD-101", request.item(), request.quantity());

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(created);
    }

    public record CreateOrderRequest(
            @NotBlank String item,
            @Min(1) int quantity) {
    }

    public record OrderView(
            String id, String item, int quantity) {
    }
}
~~~

This is a *deterministic in-memory* API purely for verifying servlet/security behavior. It **does not write to a database** or send payments/emails, so tests run without teardown. ID `ORD-101` is a hardcoded demo fixture value, not a production ID generator.

### Why not echo `X-Request-Id` from the request?

The demo emits a **server-generated** `X-Request-Id` header to illustrate `Access-Control-Expose-Headers`. In production, you may accept an upstream correlation ID, yet must validate format/length and block header injection before returning it. Never reflect untrusted user input into response headers carelessly.

### Validation is independent of security

`@Valid @RequestBody` uses `@NotBlank` and `@Min(1)`. When a user with the right role and valid CSRF sends `{"item":"","quantity":0}`, Spring MVC validation fails with **400**. Before reaching this step, the Security Filter Chain can still return 401/403. Tests must isolate each condition rather than assuming every invalid POST yields 400.

## 9. `ApiValidationAdvice.java`: MVC errors differ from Security Filter errors

**`src/main/java/com/example/securitylab/ApiValidationAdvice.java`**

~~~java
package com.example.securitylab;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidRequest(
            MethodArgumentNotValidException exception) {

        // Never expose binding values, stack traces, or
        // exception.getMessage() in public responses.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
}
~~~

Here `@RestControllerAdvice` handles only **MVC-raised validation errors**. Meanwhile, `AuthenticationEntryPoint` and `AccessDeniedHandler` handle errors from the security filter chain. A `@ControllerAdvice` does not automatically catch `AuthenticationException`/`AccessDeniedException` intercepted and handled before `DispatcherServlet`.

When production requires a unified RFC 9457 Problem Details error schema, you can use `ProblemDetail`/`ResponseEntityExceptionHandler` for MVC and render matching JSON inside the security entry point/denied handler. Never **edit only `@RestControllerAdvice` assuming 401/403 formats changed too**.

### Safe error mapping policy

| Code | Body in demo | Handler source |
| --- | --- | --- |
| 401 | `{"code":"AUTH_REQUIRED"}` | `AuthenticationEntryPoint` |
| 403 due to missing role | `{"code":"ACCESS_DENIED"}` | `AccessDeniedHandler` |
| 403 due to CSRF | Not guaranteed to match the same JSON code; verify status/CSRF behavior | `CsrfFilter`/handler per config |
| 403 due to CORS | Body may be `Invalid CORS request`, bypassing API auth JSON | `CorsFilter` |
| 400 due to validation | `{"code":"INVALID_INPUT"}` | `@RestControllerAdvice` |

Why CSRF and CORS bodies can differ: those filters **can terminate the request before** it reaches your custom JSON error handlers. Customize each layer intentionally if your API contract mandates a uniform JSON schema, rather than asserting implicit assumptions.

## 10. Test 1: positive, negative, and authenticated CORS

**`src/test/java/com/example/securitylab/CorsPolicyTest.java`**

~~~java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = SecurityLabApplication.class)
@AutoConfigureMockMvc
class CorsPolicyTest {

    private static final String TRUSTED =
            ApiSecurityConfig.ALLOWED_ORIGIN;

    private static final String UNTRUSTED =
            "https://untrusted.example.test";

    @Autowired
    private MockMvc mvc;

    @Test
    void preflightSucceedsWithoutAuthorizationOrCsrf()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type,x-request-id"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    TRUSTED))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                    "true"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("POST")))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                    containsString("authorization")))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_MAX_AGE,
                    "600"));
    }

    @Test
    void untrustedOriginPreflightIsDenied()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, UNTRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void disallowedHttpMethodPreflightIsDenied()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "DELETE"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void disallowedRequestHeaderPreflightIsDenied()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "POST")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "X-Admin-Override"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void allowedOriginCanReadPublicExposedHeader()
            throws Exception {

        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                TRUSTED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                "X-Request-Id"))
            .andExpect(header().string(
                "X-Request-Id", "server-generated-demo"))
            .andExpect(jsonPath("$.message")
                .value("public-ok"));
    }

    @Test
    void trustedOriginDoesNotBypassAuthentication()
            throws Exception {

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                TRUSTED))
            .andExpect(jsonPath("$.code")
                .value("AUTH_REQUIRED"));

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                TRUSTED))
            .andExpect(jsonPath("$[0].id")
                .value("ORD-001"));
    }

    @Test
    void untrustedActualOriginRejectedEvenForPublicPath()
            throws Exception {

        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, UNTRUSTED))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void ordinaryRequestWithoutOriginNeedsNoCorsHeader()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

### 10.1. What does the preflight test actually guard?

`preflightSucceedsWithoutAuthorizationOrCsrf` **sends no `Authorization`, session cookie, or CSRF token**, yet receives a valid CORS response. That is what browsers need before sending the real POST. If CORS ran after authentication, this test would fail with 401; if CSRF mistakenly blocked OPTIONS, it would fail with 403.

**You do not need `@RequestMapping(method=OPTIONS)` in the controller.** `CorsFilter` can return the preflight response before reaching the controller. The test sends OPTIONS directly to verify the policy itself.

### 10.2. Three negative cases with distinct meanings

- **Unknown origin:** browsers from `https://untrusted.example.test` are rejected by the allowlist.
- **Method DELETE:** origin is trusted yet policy permits only GET/POST, so browser DELETE requests are disallowed.
- **Header `X-Admin-Override`:** method is allowed yet the header is absent from `allowedHeaders`, so preflight must fail.

Never collapse all three variables into one test. If one request has both a bad origin and a bad method, a 403 test **does not tell you which policy actually worked**.

### 10.3. Trusted origins must still authenticate

`trustedOriginDoesNotBypassAuthentication` demonstrates the exact spot people confuse: a GET to a protected endpoint from a valid origin still returns 401 without credentials; once valid HTTP Basic is supplied, it returns 200. `Access-Control-Allow-Origin` can still appear on the 401 response so the trusted frontend can **read the auth error**. That is not a security hole; 401 remains enforced.

### 10.4. What if there is no Origin?

A server-side client or curl may omit `Origin`. `GET /api/public` still returns 200; CORS headers do not appear because **no cross-origin check occurred**. This reinforces that CORS is a browser sharing policy, not a general access-control gate.

## 11. Test 2: default and opt-in security headers

**`src/test/java/com/example/securitylab/SecurityHeaderTest.java`**

~~~java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = SecurityLabApplication.class)
@AutoConfigureMockMvc
class SecurityHeaderTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void defaultSecurityHeadersExistOnSuccess()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")))
            .andExpect(header().string(
                "X-XSS-Protection", "0"));
    }

    @Test
    void configuredPolicyHeadersAreReturned()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP))
            .andExpect(header().string(
                "Referrer-Policy", "no-referrer"))
            .andExpect(header().string(
                "Permissions-Policy",
                "camera=(), microphone=(), "
                + "geolocation=()"));
    }

    @Test
    void hstsIsPresentOnlyWhenRequestIsSecure()
            throws Exception {

        mvc.perform(get("/api/public").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=31536000")));

        mvc.perform(get("/api/public").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }

    @Test
    void unauthorizedResponsesKeepSecurityHeaders()
            throws Exception {

        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP))
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")));
    }

    @Test
    void authorizationDeniedStillHasSecurityHeaders()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("reader").roles("READER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"item\":\"Java book\",\"quantity\":2}"))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP));
    }

    @Test
    void validationErrorsStillHaveSecurityHeaders()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"item\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                ApiSecurityConfig.CSP));
    }
}
~~~

### 11.1. What is default vs explicitly configured?

In Spring Security 6.3:

- `X-Content-Type-Options: nosniff` is a default.
- `X-Frame-Options: DENY` is a default.
- `Cache-Control` preventing caching is a default in standard scenarios, though apps may override it.
- `X-XSS-Protection: 0` indicates not relying on the legacy XSS filter.
- `Strict-Transport-Security` is written **when the request is recognized as secure**.
- `Content-Security-Policy`, `Referrer-Policy`, and `Permissions-Policy` appear in the demo because **`SecurityConfig` enabled them explicitly**.

If the team deletes `headers(...contentSecurityPolicy...)` from config and the CSP test still passes, the test is broken or hitting another context/mock. A useful **mutation test** is temporarily deleting the policy on a local branch to prove the test fails, then reverting.

### 11.2. Security headers on error paths

Do not check only 200 responses. Protected endpoints returning 401 or 403, and controllers returning 400, still need protective headers. Security headers reduce clickjacking, content sniffing, or caching risks **on error responses as well**. Never test only happy paths assuming filters run uniformly on every exception path.

### 11.3. HSTS in reverse proxy deployments

`MockHttpServletRequest.secure(true)` simulates a request recognized as HTTPS. This verifies **application-layer HSTS header writing**, not whether ingress/nginx/load balancers forward `X-Forwarded-Proto` or `Forwarded` properly. When production terminates TLS upstream, test directly through the proxy over real HTTPS and ensure untrusted forwarded headers are rejected.

## 12. Test 3: 401, 403, CSRF, and input validation

**`src/test/java/com/example/securitylab/SecurityFailureTest.java`**

~~~java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(
    classes = SecurityLabApplication.class)
@AutoConfigureMockMvc
class SecurityFailureTest {

    @Autowired
    private MockMvc mvc;

    private static final String VALID_ORDER =
            "{\"item\":\"Java book\",\"quantity\":2}";

    @Test
    void missingAuthenticationReturns401Json()
            throws Exception {

        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", "Basic realm=\"demo\""))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code")
                .value("AUTH_REQUIRED"));
    }

    @Test
    void invalidBasicCredentialsReturn401()
            throws Exception {

        mvc.perform(get("/api/orders")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTH_REQUIRED"));
    }

    @Test
    void readerCanAccessReadOnlyEndpoint()
            throws Exception {

        mvc.perform(get("/api/orders")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id")
                .value("ORD-001"));
    }

    @Test
    void editorCanAccessReadOnlyEndpoint()
            throws Exception {

        mvc.perform(get("/api/orders")
                .with(httpBasic("editor", "editor-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].item")
                .value("Java book"));
    }

    @Test
    void readerCannotCreateEvenWithValidCsrf()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("reader").roles("READER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code")
                .value("ACCESS_DENIED"));
    }

    @Test
    void editorWithoutCsrfIsDeniedBeforeController()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithInvalidCsrfIsDenied()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithCsrfAndValidBodyCanCreate()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_ORDER))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id")
                .value("ORD-101"))
            .andExpect(jsonPath("$.quantity")
                .value(2));
    }

    @Test
    void invalidBodyReturns400OnlyAfterSecurityPasses()
            throws Exception {

        mvc.perform(post("/api/orders")
                .with(user("editor").roles("EDITOR"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"item\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_INPUT"));
    }

    @Test
    void authenticatedUserStillCannotAccessDenyAllPath()
            throws Exception {

        mvc.perform(get("/api/internal")
                .with(user("editor").roles("EDITOR")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code")
                .value("ACCESS_DENIED"));
    }

    @Test
    void publicEndpointDoesNotRequireCredentials()
            throws Exception {

        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                .value("public-ok"));
    }
}
~~~

### 12.1. Why are `user()` and `httpBasic()` used differently?

- `httpBasic("reader","reader-pass")` adds a real **`Authorization` Basic header** to the MockMvc request. The test runs through the Basic authentication filter and `UserDetailsService`, catching credential/password issues.
- `user("reader").roles("READER")` is a Spring Security test request post-processor setting identity/authorities for the test. It fits **authorization/CSRF** tests without repeating login logic, yet **does not** prove `reader`'s password works.
- `csrf()` generates a valid token for the MockMvc request; `csrf().useInvalidToken()` exercises rejection paths.
- `@WithMockUser` is also useful at method/class scope, provided you understand it mocks the security context rather than performing real login.

Therefore, authentication tests should send Basic headers, while authorization tests can use `user()`. One request mechanism does not substitute for the other across all goals.

### 12.2. 401 and 403 errors

**401** reflects unauthenticated requests or bad credentials (on protected endpoints). With Basic auth, `WWW-Authenticate` is the matching challenge. **403** reflects an authenticated identity lacking permissions in role-specific tests, or requests rejected by CSRF/CORS.

One subtlety: on a **POST without CSRF**, the filter may return **403 before Spring evaluates authentication**. Therefore, avoid writing tests asserting “anonymous POST must always return 401”. To test authentication cleanly, use a protected GET or include valid CSRF to pass the CSRF filter.

### 12.3. Validation 400 occurs only after reaching MVC

`invalidBodyReturns400OnlyAfterSecurityPasses` sends role `EDITOR` + a valid CSRF token so the request reaches the controller and validation. Omitting `csrf()` shifts expected 400 to **403** because the controller never sees the body. A red test there is right: the security filter is still doing its job.

### 12.4. Testing `denyAll` is defense-in-depth

Even `EDITOR` cannot `GET /api/internal` because of `anyRequest().denyAll()`. This protects against developers adding new endpoints while forgetting to update allowlist rules. In production, authorization still requires path-by-path review, permission models, and domain rules; a trailing `denyAll` does not prove service-layer authorization is correct.

## 13. Expected results and how to run

The project has **25 `@Test` methods**:

| Test class | Test count | Goal |
| --- | ---: | --- |
| `CorsPolicyTest` | 8 | Trusted/untrusted origins, preflight, methods/headers, browser errors |
| `SecurityHeaderTest` | 6 | Defaults, opt-in headers, HTTPS/HSTS, error responses |
| `SecurityFailureTest` | 11 | 401, Basic credentials, roles, CSRF, validation, `denyAll` |
| **Total** | **25** | Spring Security filter chain + MVC assertions |

### Running with Gradle

JDK 17 and a compatible Gradle Wrapper belong in the project root:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run a single class:

~~~bash
./gradlew test --tests 'com.example.securitylab.CorsPolicyTest'
./gradlew test --tests 'com.example.securitylab.SecurityHeaderTest'
./gradlew test --tests 'com.example.securitylab.SecurityFailureTest'
~~~

JUnit reports typically appear at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.securitylab.CorsPolicyTest.xml
    ├── TEST-com.example.securitylab.SecurityHeaderTest.xml
    └── TEST-com.example.securitylab.SecurityFailureTest.xml
~~~

**Expected:** With compatible source and dependencies, **25 JUnit test methods are expected to pass**. This is an **expectation from design**, not a claim that Gradle ran in the reader's environment. The code contains no `System.out.println`, so there is no fixed business stdout. If Gradle reuses `UP-TO-DATE`/`FROM-CACHE`, force re-execution when diagnosing:

~~~bash
./gradlew test --rerun-tasks
~~~

If no Wrapper exists yet and a compatible Gradle is installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Commit the Wrapper scripts/JAR per repo policy. Never alter the Gradle version on a real application merely because an example suggests one.

### Why is `@ExtendWith(SpringExtension.class)` unnecessary?

`@SpringBootTest` integrates Spring `TestContext`/JUnit Jupiter through meta-annotations. `@AutoConfigureMockMvc` creates the `MockMvc` bean wired to the Spring context. You do not need `MockMvcBuilders.standaloneSetup(...)`, which **does not attach Spring Security's `FilterChainProxy`** if you forget `springSecurity()`/filters.

### Why avoid `@AutoConfigureMockMvc(addFilters=false)`?

Because `addFilters=false` **removes Security filters** from the MockMvc pipeline, causing CORS, CSRF, header, and authorization tests to **turn falsely green or fail due to unenforced policies**. In this lesson, we keep `@AutoConfigureMockMvc`'s default `addFilters=true`. That is the heart of security integration testing.

## 14. Real HTTP smoke tests with curl

MockMvc suffices for testing servlet filter behavior, yet does not open a real socket. To inspect actual HTTP bytes in a dev/sandbox environment, start the app:

~~~bash
./gradlew bootRun
~~~

In another terminal, target localhost HTTP using the **test-only demo accounts**.

### Public endpoint

~~~bash
curl -i http://localhost:8080/api/public
~~~

Expect status 200, JSON body `{"message":"public-ok"}`, and the security headers. Over plain HTTP, HSTS is **absent** by default.

### 401 without credentials

~~~bash
curl -i http://localhost:8080/api/orders
~~~

Expect 401, `WWW-Authenticate: Basic realm="demo"`, and JSON `AUTH_REQUIRED`.

### 200 with test Basic credentials

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/orders
~~~

Expect 200 and a JSON array containing order `ORD-001`. **Never run commands with real passwords in shell history or CI logs**; these are demo credentials only.

### Allowed CORS preflight

~~~bash
curl -i -X OPTIONS \
  http://localhost:8080/api/orders \
  -H 'Origin: https://portal.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

Expect 200 with `Access-Control-Allow-Origin: https://portal.example.test`. No credentials are required for preflight.

### Denied CORS preflight

~~~bash
curl -i -X OPTIONS \
  http://localhost:8080/api/orders \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: POST'
~~~

Expect 403. **No** `Access-Control-Allow-Origin` for this origin. Curl prints the HTTP response without enforcing browser CORS policy; the browser decides whether JavaScript may read the response.

### POST with CSRF

In the lab, generating CSRF tokens with `csrf()` is easiest inside MockMvc. Sending a curl POST without a token to a CSRF-enabled API normally gets 403; that is expected. A real browser session needs a proper mechanism to fetch and send CSRF tokens (meta tags, cookie token repository, form tokens, or a securely designed CSRF endpoint). **Never disable CSRF just so a curl POST returns 201.**

## 15. True security tests must include negative assertions

Some tests only verify allowed access:

~~~java
mvc.perform(get("/api/public"))
    .andExpect(status().isOk());
~~~

This test will not detect a policy allowing every origin onto protected resources. Test the **opposite**:

~~~java
mvc.perform(options("/api/orders")
        .header("Origin",
                "https://untrusted.example.test")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

Negative cases should vary **one invalid variable at a time**: origin, method, header, credentials, role, CSRF, or body. Mixing bad origin + bad role + missing CSRF in one request can yield 403 even when the component under test is disabled, creating false positives.

### Manual mutation testing

A quick review technique:

1. Temporarily add an unknown origin to the allowlist — the untrusted-origin test must turn red.
2. Temporarily add `DELETE` to `allowedMethods` — the disallowed-method test must turn red.
3. Temporarily add `X-Admin-Override` to `allowedHeaders` — the disallowed-header test must turn red.
4. Temporarily remove `http.cors` — the allowed-preflight test must turn red.
5. Temporarily remove `.hasRole("EDITOR")` on POST — the reader-forbidden test must turn red.
6. Temporarily set `csrf.disable()` — the CSRF-rejection tests must turn red.
7. Temporarily omit CSP directives — the CSP header tests must turn red.
8. Temporarily remove Basic authentication — the authentication/basic tests must turn red.

Revert every mutation; never merge intentionally weakened code. A test suite only proves high value when it passes when right **and fails when the guarded policy breaks**.

## 16. HSTS, HTTPS, and reverse proxies

HSTS instructs browsers to use HTTPS for a hostname for a configured duration. Spring Security emits this header by default on HTTPS requests, typically with `max-age=31536000` and `includeSubDomains` depending on config.

### Why HTTPS-only?

Browsers should learn HSTS only over a valid HTTPS connection, preventing attackers on HTTP paths from injecting arbitrary policies. The lesson uses `.secure(true)` to simulate a secure servlet request. That verifies **`HeaderWriter` behavior**, yet does not test:

- TLS certificate chains/hostnames/SNI.
- Reverse proxies terminating client HTTPS and forwarding HTTP upstream.
- Whether `Forwarded`/`X-Forwarded-Proto` headers are trusted only from authorized proxies.
- HTTP->HTTPS redirect policy.
- HSTS presence on CDN/nginx responses, not just the app.
- Whether HSTS `includeSubDomains` affects subdomains outside your team's HTTPS control.

### Production test scenario

If the frontend reaches `https://api.example.com` through ingress, run an HTTPS smoke test through the real ingress or equivalent sandbox:

1. TLS handshake/certificate is valid.
2. Responses do not enter redirect loops.
3. HSTS carries the expected policy directives.
4. CORS matches the frontend origin accurately.
5. Arbitrary client-sent `X-Forwarded-Proto: https` headers from outside trusted proxies are ignored.
6. Security headers are not overwritten improperly by ingress.
7. HTML/JSON error pages retain the policies where applicable.

Do not enable `preload`/`includeSubDomains` without auditing every host/subdomain and the organization's HTTPS readiness.

## 17. CORS preflight caching, Vary, and reverse proxies

Browsers can cache preflight results per `Access-Control-Max-Age` (600 seconds in the demo), subject to browser caps. Consequently:

- Changing CORS policy may not immediately affect browsers holding cached preflights.
- CDNs/reverse proxies must key caches properly on `Origin`, requested method, and requested headers.
- `Vary: Origin` and related headers prevent caches from mixing responses across origins.
- A misconfigured CDN can serve Origin A's CORS headers to Origin B.
- `Access-Control-Max-Age` is not business response `Cache-Control`; they govern separate caches.

### How should `Vary` be tested?

In an integration test with a CORS processor, you can check that responses carry relevant `Vary` values. However, how frameworks merge headers into one line or multiple lines varies by servlet container. Do not assert a single exact string when multiple valid HTTP header list formats exist. Protecting real caches requires testing through the CDN/proxy or dedicated cache config tests.

### CORS with multiple SecurityFilterChain beans

If an app defines multiple chains (e.g., `/api/**` bearer JWT, `/admin/**` form login), each chain has its own security matcher. CORS configuration must be attached to each chain needing it; a chain missing `cors` or holding higher priority can return 401 on overlapping preflights.

In multi-chain projects, build a CORS matrix per **path and chain**. Never assume that because `/api/orders` preflight passes, `/admin/orders` works too.

## 18. CSRF, cookie authentication, and SameSite

CSRF and CORS are often confused:

- **CORS** governs cross-origin JavaScript reading responses and certain request flows.
- **CSRF** stops browsers from automatically attaching ambient credentials to state-changing actions not explicitly authorized by the user.
- **The `SameSite` cookie attribute** mitigates cross-site cookie sending, yet is not a blanket excuse to drop CSRF tokens.
- **Authentication** verifies identity.
- **Authorization** checks the identity's permissions.

In the demo, POST requires role `EDITOR` and a valid CSRF token. `csrf()` from `spring-security-test` supplies a valid test token; there is no need to disable CSRF to test authorization.

### Allowed CORS origin does not mean POST always succeeds

From `https://portal.example.test`, preflight can return 200 because policy permits POST with `Authorization`/`Content-Type`. Yet the main request can still return:

- 401 if Basic credentials are missing;
- 403 if the role is `READER`;
- 403 if the role is `EDITOR` without CSRF;
- 400 if `EDITOR` has CSRF yet invalid JSON;
- 201 if `EDITOR` has CSRF and valid JSON.

This is **expected behavior** when multiple protection layers cooperate. A frontend must handle both browser network-level CORS blocks and HTTP JSON errors exposed when CORS allows reading responses.

### When should CSRF be disabled for an API?

A stateless API accepting only Bearer tokens in the `Authorization` header, without cookies, sessions, or ambient browser credentials, may not require CSRF like cookie-session apps. Base the decision on **threat model**, authentication transport, and clients — never merely on the fact that the API returns JSON.

When disabling CSRF intentionally, add tests confirming endpoints remain guarded by **Bearer authentication/authorization** and do not open anonymously. Never copy `.csrf(csrf -> csrf.disable())` into every Spring REST app just because a 403 appeared.

## 19. Authentication errors: prevent account enumeration

Good authentication error responses expose consistent public details. Bad example:

~~~json
{"message":"User alice@example.com exists but entered wrong password"}
~~~

This leaks user existence. Likewise:

~~~json
{"message":"User not found in table internal_users where id=..."}
~~~

leaks database schema. In our demo API:

~~~json
{"code":"AUTH_REQUIRED"}
~~~

applies to both **missing credentials** and **wrong Basic password**. Internal logs can record the error type, request ID, and sanitized context for investigation. Never log raw `Authorization` headers, cookies, passwords, tokens, or out-of-policy PII.

### `WWW-Authenticate` header

HTTP Basic uses `WWW-Authenticate: Basic realm="demo"` on 401. For OAuth2 Resource Server / Bearer tokens, responses typically return a Bearer-scheme challenge with error codes per RFC 6750. **Do not reuse Basic challenges** when the real app uses JWT/OAuth2.

When migrating tests to JWT, verify:

- Missing Bearer token -> 401.
- Invalid signature/expired/wrong issuer/audience token -> 401 per config.
- Valid token lacking scope/authority -> 403.
- Valid token with required scope -> 200/201.
- Error body leaks no signed token, secret, or internal exception.
- CORS preflight still runs before authentication.

In Spring Security, `spring-security-test` offers `jwt()`/`opaqueToken()` request post-processors for unit/integration authorization tests, yet they **do not prove token decoders or remote JWKS HTTP validation**. When testing the decoder, write dedicated auth-server/JWKS wiring tests.

## 20. Authorization: role checks alone are insufficient for multi-tenant data

Role `EDITOR` allows posting orders in the lab. Production usually also needs **object-level authorization**:

- Tenant A's editor cannot read Tenant B's orders.
- Users can modify only accounts belonging to their organization.
- Admin roles may apply only within one data domain.
- Services must verify ownership before writing, not only the request path.
- Repository queries must filter by tenant ID/ACL accurately.
- Never leak sensitive data via IDOR (`/api/orders/{otherTenantId}`).

These checks require **service/data-layer integration tests** with user/tenant fixtures, pairing `@WithMockUser`/JWT claims or real authentication mechanisms. Tests covering only HTTP role matchers do not prove full ABAC/ownership policies.

### Trailing `denyAll`

Using `anyRequest().denyAll()` ensures newly added unmapped endpoints are blocked by default. That is defense-in-depth, not a permission model replacement. When opening `permitAll()` for health/docs/static assets, review each path and role individually rather than opening `/**` just to get the API running.

## 21. Security error handling and Problem Details

Spring Framework provides `ProblemDetail` to represent HTTP API errors per the Problem Details standard. Since security filters do not flow automatically through `@RestControllerAdvice`, if a team wants one shared schema across MVC and Security, you must:

1. Design a stable public error schema (e.g., `type`, `title`, `status`, `code`, `requestId`).
2. Configure `AuthenticationEntryPoint` to produce 401 responses.
3. Configure `AccessDeniedHandler` to produce authorization 403 responses.
4. To return JSON for CSRF 403, configure the handler at the filter layer and re-test all paths; do not assume one role-denied handler covers every CSRF scenario.
5. To return JSON on CORS rejections, customize the CORS processor/filter appropriately; remember browsers prevent JS from reading responses from rejected origins anyway.
6. Handle MVC validation/business exceptions in `@RestControllerAdvice`.
7. Test security headers, content types, and leaked info across all error paths.

### Status codes never to change arbitrarily

- Missing/invalid credentials on protected endpoints: **401**, never swap to 403 just to “suppress a Basic browser popup” when the auth contract requires a challenge.
- Authenticated yet unauthorized: **403**.
- Invalid JSON/body after security: **400** (or another status when explicitly contracted).
- Rate limiting: **429 Too Many Requests**, not an auth failure.
- Internal exception: **500**, generic error, no stack trace.
- CORS forbidden: server may emit 403, though **browser JS cannot necessarily read the body**.

Never surface raw exception details from `AccessDeniedException`, JWT parsing, databases, LDAP, or authorization services in responses. Keep detailed reasons in access-controlled logs/traces.

## 22. When to test with `@WebMvcTest`?

Full-context `@SpringBootTest` boots all application beans, whose speed depends on app size. `@WebMvcTest` can be great for testing MVC controller binding/validation, yet **security testing** carries important caveats:

- Spring Boot's MVC slice may include security config/filters depending on component scans and auto-configurations.
- If the project places a custom `SecurityFilterChain` in a `@Configuration` omitted by slice scanning, add `@Import(ApiSecurityConfig.class)` or configure explicitly so the right chain runs.
- Using `@AutoConfigureMockMvc(addFilters=false)` skips security filter testing altogether.
- If the controller injects services outside the MVC slice, use `@MockBean` (Boot 3.3)/`@MockitoBean` in newer Spring Framework versions or matching test configs.
- Pure controller unit tests cannot replace **real bean wiring/CORS/filter-chain tests** when those are part of the contract.
- With multiple chains, slices can load only partially and give false confidence.

**Choose the smallest test that still proves the contract**, without stripping out the very component you aim to verify. In this lesson, full-context MockMvc keeps the complete real `SecurityConfig` active without booting a browser or server port.

### When `RANDOM_PORT` or browser E2E is needed

MockMvc exercises the servlet pipeline **without opening a real TCP socket**. Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` plus an HTTP client or Playwright/browser when your goals include:

- Session cookie `SameSite`, `Secure`, `HttpOnly` across real browsers;
- Real Fetch API CORS enforcement;
- TLS handshakes, HSTS over HTTPS, and reverse proxies;
- HTTP redirects, caching, and CDN behavior;
- Network authentication proxies / forwarded headers;
- Cookie domain/path and credential modes;
- HTTP/2 or WebSocket handshakes.

Never claim a MockMvc header assertion constitutes end-to-end network security verification.

## 23. Diagnosing failed CORS and security tests

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Browser `OPTIONS` returns 401 | CORS runs after auth or filter chain lacks `cors` | Configure `http.cors(...)` and source on the right chain/path |
| `OPTIONS` returns 403 even with right origin | Method/request header missing from allowlist | Inspect actual `Access-Control-Request-Method/Headers` |
| POST works in Postman, fails CORS in browser | Postman/curl do not enforce CORS | Check `Origin`/preflight + browser DevTools |
| Preflight returns 200 yet browser still blocks | Missing matching ACAO/ACAH/ACAM/ACAC | Inspect actual response headers, not just status |
| Enabled `allowCredentials` with `*` origin | Wildcard/credential conflict | Use exact origin allowlist or vetted patterns |
| Works on localhost, fails on staging | Scheme/port/subdomain differs | Configure exact origin per environment |
| CORS 403 lacks `ACCESS_DENIED` JSON body | `CorsFilter` rejected before security handlers | Check policy and filter; do not force auth JSON error |
| Reader POST gets 403 before role check | Missing CSRF | Add `csrf()` in role-specific tests |
| Anonymous POST gets 403 instead of 401 | `CsrfFilter` runs before authentication | Test 401 via protected GET or request with valid CSRF |
| Invalid JSON POST returns 403 instead of 400 | Missing auth/role/CSRF | Satisfy security checks before testing validation |
| 401 lacks `WWW-Authenticate` | Custom entry point omits Basic challenge | Configure entry point matching auth scheme |
| Role-denied 403 returns 401 | User unauthenticated or wrong test principal setup | Use `httpBasic`/`user` matching test goal |
| 200 without credentials | Filters disabled or `permitAll` too broad | Check `@AutoConfigureMockMvc` filters and `SecurityFilterChain` |
| `nosniff`/`X-Frame-Options` missing | `HeaderWriterFilter` bypassed or disabled | Inspect chain, headers config, and filters |
| CSP missing | CSP is not enabled by default | Configure `contentSecurityPolicy` explicitly |
| Referrer/Permissions missing | Not opted in | Configure via headers DSL |
| HSTS missing on HTTP MockMvc | Expected default: HSTS is HTTPS-only | Use `secure(true)`; test proxy/TLS separately |
| HSTS missing behind HTTPS ingress | Wrong forwarded headers / proxy trust | Verify trusted proxy config and HTTPS smoke test |
| Headers appear on 200 yet vanish on 500 | Error dispatch/ingress/another chain | Test real error paths + filter registration |
| Browser still hits XSS despite CSP | CSP does not replace output encoding/DOM sanitization | Audit sinks, CSP directives, and browser tests |
| Tenant A's `Origin` header leaks to Tenant B | Misconfigured CDN `Vary` caching | Verify cache keys include `Origin` |
| Tests pass when security is disabled | Tests only mock controllers / disable filters | Use MockMvc `addFilters=true` and negative tests |
| Single test passes, suite fails | Shared `SecurityContext`/cookies/MockMvc state | Isolate tests, avoid mutating global state |
| 401 body leaks stack trace/password | Error handler echoes exception | Use stable error codes, sanitize logs |
| `AUTH_REQUIRED` JSON fails for wrong password | `BasicAuthenticationFilter` uses a different entry point | Align Basic entry point and exception handling |

### Systematic debugging

1. Record method, path, `Origin`, `Access-Control-Request-*`, `Authorization` presence, and CSRF presence (never log secret values).
2. Determine whether the request is a **CORS preflight**.
3. Check whether the request matched the intended `SecurityFilterChain`.
4. Check whether `CorsConfigurationSource` covers the right path/origin/method/header.
5. Check whether CSRF blocked an unsafe request before auth/authorization.
6. Distinguish anonymous vs authenticated principals.
7. Check role/authority prefixes, HTTP method matchers, and `denyAll`.
8. Identify whether response headers and error bodies come from CORS, Security, or MVC.
9. If headers are missing, determine whether a filter was skipped or error dispatch hit a different chain.
10. If only browsers fail, inspect browser DevTools and real HTTPS/cookie/credentials modes.
11. If tests seem suspiciously green, temporarily break policy to confirm negative tests fail.
12. Never drop in `permitAll()` or `csrf.disable()` as a blind fix before finding root cause.

## 24. Threat-model-driven test matrix

A production test suite does not pick status codes out of habit. Identify client types, data sensitivity, and the threat model:

| Threat | Test objective | Example |
| --- | --- | --- |
| Cross-origin data read | CORS origin allowlist/credentials | Origin outside trusted list receives no ACAO |
| CSRF | Unsafe methods need token with cookies/sessions | POST without token gets 403 |
| Unauthorized API access | Authentication on protected paths | Protected GET without credentials gets 401 |
| Privilege escalation | Role/permission checks | READER POST gets 403 even with valid CSRF |
| IDOR | Ownership/tenant checks | User A cannot read User B's entity |
| Clickjacking | `X-Frame-Options`/CSP `frame-ancestors` | `DENY` / `frame-ancestors 'none'` |
| MIME confusion | `X-Content-Type-Options` | `nosniff` |
| XSS | Output encoding/CSP | CSP present, browser script sources restricted |
| Sensitive data caching | `Cache-Control` | `no-store` on sensitive responses |
| TLS downgrade | HSTS/HTTPS | HSTS on secure requests, HTTPS ingress verified |
| Information disclosure | Error JSON/logging | No stack traces, secrets, or SQL queries |
| Wrong CORS cache | `Vary`/CDN behavior | Origin A never reuses cached headers for B |
| Accidentally exposed endpoint | Deny-by-default | Unknown path/role never receives 200 |

Not every API requires identical CSP or `Permissions-Policy`. Still, every security decision should have a **clear rationale and assertions capable of catching regressions**.

## 25. Practice exercises

**Exercise A — Break preflight:** Remove `http.cors(Customizer.withDefaults())` on a test branch. Run `CorsPolicyTest` and explain why preflight no longer returns the expected ACAO headers.

**Exercise B — Wrong origin:** Add `https://untrusted.example.test` to allowed origins and run negative tests. Tests must catch the unintended policy widening.

**Exercise C — Method allowlist:** Add `DELETE` to `allowedMethods` without adding a DELETE controller. Contrast how CORS preflight can pass while actual DELETE gets 403/404/405 due to authorization/controller mapping.

**Exercise D — Request header allowlist:** Add `X-Admin-Override` to `allowedHeaders`. The negative preflight test must turn red, proving tests guard configuration.

**Exercise E — Credentials/wildcard:** Try `setAllowedOrigins(List.of("*"))` alongside `setAllowCredentials(true)` in a test environment. Observe the configuration failure and explain why it is rejected for credentialed requests.

**Exercise F — Header exposure:** Remove `setExposedHeaders(List.of("X-Request-Id"))`. `allowedOriginCanReadPublicExposedHeader` must fail even though the HTTP response still contains `X-Request-Id`.

**Exercise G — 401 vs 403:** Compare `httpBasic("reader","wrong-password")` against `user("reader").roles("READER")` POST + CSRF. Distinguish authentication failure from authorization failure.

**Exercise H — CSRF:** Remove `with(csrf())` on the `EDITOR` POST test. Expected 201 turns into 403. Never alter the matcher to expect 403 just to keep a success-path test green.

**Exercise I — Invalid token:** Try `with(csrf().useInvalidToken())`, verifying rejection even when authentication and role are valid.

**Exercise J — Validation path:** Use `EDITOR` + valid CSRF with `item=""` and `quantity=0`. Test must return 400 `INVALID_INPUT`. Then remove `csrf()` and observe 403 firing before MVC.

**Exercise K — Headers on errors:** Remove `headers(...ContentSecurityPolicy...)`. Verify 200/401/403/400 tests all detect missing CSP.

**Exercise L — HSTS:** Replace `.secure(true)` with a plain HTTP request. Explain why HSTS is absent and why HTTPS integration smoke tests through the reverse proxy are needed.

**Exercise M — Deny all:** Temporarily replace `anyRequest().denyAll()` with `permitAll()`. Confirm `/api/internal` must not be publicly exposed.

**Exercise N — Cookie credentials:** Design an application test with session cookies and a CSRF token repository, then run browser E2E checks on `SameSite`, `Secure`, `HttpOnly`, credentials mode, and CORS.

**Exercise O — Multi-tenancy:** Build `GET /api/orders/{id}` backed by a test DB holding orders for two tenants. Tenant A's `READER` must not read Tenant B even when authenticated.

**Exercise P — JWT/Bearer:** Replace the Basic demo with a Resource Server. Write tests for missing/invalid/expired tokens -> 401, missing scope -> 403, valid scope -> 200, while preflight still passes.

**Exercise Q — ProblemDetail:** Adopt one unified JSON error schema for auth/forbidden/validation without leaking internals. Verify filter errors are not misattributed to MVC advice.

**Exercise R — Browser CSP:** Build an HTML test page needing approved CSS/JS and test CSP in a real browser rather than asserting only the header string.

**Exercise S — CDN cache:** Build an integration test through a reverse proxy verifying one origin never receives another origin's cached ACAO.

**Exercise T — Security test mutation:** Break allowlist/role/CSRF/CSP rules one by one, confirm negative tests fail, then revert configuration.

## 26. Checklist before merging Spring Security tests

- [ ] Identified browser vs server-to-server clients and whether CORS is an actual boundary?
- [ ] Preflight `OPTIONS` runs before authentication and CSRF as appropriate?
- [ ] Allowed origins are exact/controlled without echoing `Origin` unchecked?
- [ ] `allowCredentials=true` is never paired with `allowedOrigins("*")`?
- [ ] `GET`/`POST`/`DELETE` and requested headers have separate positive/negative tests?
- [ ] Preflight tests assert `Access-Control-Allow-*` headers, not just HTTP status?
- [ ] Actual cross-origin response tests assert ACAO and `Expose-Headers` where needed?
- [ ] Disallowed-origin tests verify no ACAO header is returned?
- [ ] Remembered that CORS never replaces authorization?
- [ ] Tested anonymous 401, bad credentials 401, and authenticated unauthorized 403?
- [ ] Role/controller tests include `csrf()` when testing behaviors past CSRF?
- [ ] Tested missing/invalid CSRF causing 403 on unsafe methods?
- [ ] Validation tests supply valid user/role/CSRF so execution truly reaches MVC?
- [ ] `AuthenticationEntryPoint` and `AccessDeniedHandler` emit safe public JSON?
- [ ] `@RestControllerAdvice` is not mistakenly assumed to handle security filter errors?
- [ ] Basic/Bearer authentication emits `WWW-Authenticate` with the right scheme if required?
- [ ] Verified `X-Content-Type-Options: nosniff`?
- [ ] Verified `X-Frame-Options: DENY` or matching frame policy?
- [ ] Verified `Cache-Control` protects sensitive responses?
- [ ] Verified HSTS on HTTPS requests rather than forcing it on plain HTTP?
- [ ] Enabled CSP/Referrer/Permissions policies in app config when required by tests?
- [ ] Confirmed security headers persist on 401/403/400 responses?
- [ ] `@AutoConfigureMockMvc` keeps filters enabled (`addFilters=true`)?
- [ ] Security tests do not rely entirely on mocked `SecurityFilterChain` beans?
- [ ] With multiple security chains, tested CORS/authorization policies per path?
- [ ] Added network/browser tests where browser cookies and HTTPS reverse proxies apply?
- [ ] Avoided test credentials or `{noop}` in production?
- [ ] Confirmed responses/logs never leak tokens, passwords, PII, SQL, or stack traces?
- [ ] Confirmed tests run independently without shared `SecurityContext`/cookies/ordering?
- [ ] Test matrix includes negative assertions to catch policy relaxation?
- [ ] Gradle/JUnit report confirms tests actually ran rather than merely hitting task cache?

## 27. Official references

The following documents underpin the **Spring Boot 3.3.5 / Spring Security 6.3.x** examples. For Spring Security 6.4+/7.x, some DSL APIs may change or be deprecated; check the matching version before copying to production.

- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS before security, `CorsConfigurationSource`, Spring MVC integration.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): defaults, HTTPS-only HSTS, CSP, Referrer Policy, Permissions Policy.
- [Spring Security 6.3 API — HeadersConfigurer](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/config/annotation/web/configurers/HeadersConfigurer.html): `contentSecurityPolicy`, `permissionsPolicy`, header writer configuration DSL.
- [Spring Security — MockMvc Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): `springSecurity()`, request post-processors, filter registration.
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `user()`, `@WithMockUser`, and `SecurityContext`.
- [Spring Security — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html): `httpBasic()` generating `Authorization` headers for tests.
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `csrf().useInvalidToken()`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF threat model, defaults, and protection.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, servlet test scopes.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `CorsConfiguration`, `UrlBasedCorsConfigurationSource`, allowed origins/headers/methods.
- [Spring Framework — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ControllerAdvice`/`@ExceptionHandler` in MVC.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser behavior, preflight, credentials, and headers.
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security): HTTPS-only HSTS and directives.

**Remember:** A high-quality security test suite proves both **what is permitted** and **what is denied**. For CORS, test preflight and response headers across origins, methods, and headers; for security headers, verify defaults, opt-in headers, and **HSTS over HTTPS**; for errors, distinguish 401 authentication, 403 authorization/CSRF/CORS, and 400 MVC validation. Use MockMvc with the **real `SecurityFilterChain`**, keep CSRF active when it is the contract, never let error handlers leak internal details, and add browser/HTTPS/proxy tests when guarding real network boundaries.
