# Testing CSRF, CORS, and Security Headers in Spring Security

> **Scope:** Spring Security fundamentals — **Testing** section. This lesson uses Java 17+, Spring Boot 3.3.x, Spring Security 6.x, JUnit 5, Spring Security Test, and **MockMvc (Servlet/Spring MVC)**. The focus is proving both accepted and rejected cases, distinguishing the roles of CSRF/CORS/security headers, and checking defaults as well as customizations. WebFlux uses `WebTestClient` and `SecurityWebFilterChain`; differences are explained at the end.

## 1. Three mechanisms protecting against three different problems

A single "HTTP 200" test is not enough to verify browser defenses. You must understand which signal each mechanism inspects and which attacker each constrains:

| Mechanism | What risk does it prevent or mitigate? | Inputs/configuration | What to test |
| --- | --- | --- | --- |
| **CSRF** (Cross-Site Request Forgery) | Another website tricks the victim's browser into performing a state-changing action using auto-sent credentials (cookies/sessions; potentially HTTP Basic depending on browser) | CSRF token, token repository, request handler, matcher for protected methods | POST missing/wrong token is rejected; valid token proceeds; CSRF does not replace authentication |
| **CORS** (Cross-Origin Resource Sharing) | Governs which origins' browser JavaScript may read API responses, and which cross-origin requests require preflight | `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`; allowed origins/methods/headers/credentials policy | Preflight with valid origin/method/headers is allowed; bad origin is rejected; response includes matching CORS headers |
| **Security response headers** | Instructs browsers to restrict MIME sniffing, framing/clickjacking, caching of sensitive data, script/style sources, referrers, and HTTP connections | `X-Content-Type-Options`, `X-Frame-Options`, `Cache-Control`, `Content-Security-Policy`, `Referrer-Policy`, `Strict-Transport-Security`... | Default headers are present; custom CSP/Referrer are accurate; HSTS appears only when the request is treated as HTTPS |

**Three things never to conflate:**

1. **CORS is not authentication/authorization.** Requests from curl or server-to-server can send any `Origin` or none at all; CORS policies are primarily enforced by browsers, never replacing JWT/session/roles.
2. **CORS does not replace CSRF.** Allowing an origin to read an API does not mean a browser POST carried a valid CSRF token. Conversely, missing CORS headers do not necessarily stop browsers from **sending** certain state-changing requests; they may only stop scripts from reading the response.
3. **Correct headers do not prove browsers enforced every policy.** MockMvc inspects server-generated responses. Testing real CSP behavior, cookies, redirects, caching, or HTTPS proxies may require browser/E2E tests.

## 2. CSRF: valid, missing-token, and invalid-token cases

### 2.1 When does Spring Security require a token?

In Servlet applications, CSRF protection is enabled by default in standard Spring Security configurations. It normally protects **unsafe** methods such as POST, PUT, PATCH, and DELETE. Safe methods include GET, HEAD, OPTIONS, and TRACE; they **must not cause state-changing side effects**, since browsers/proxies/caches may invoke them automatically.

Typical flow:

```text
Browser sends POST /api/notes
     |
     +--> Carries session/cookie/credential per client mechanism
     |
     +--> CsrfFilter fetches expected token from CsrfTokenRepository
     |                     |
     |               reads request token
     |               (form field/header per configuration)
     |
     +--> Missing or mismatched token => AccessDeniedException
     |                                  => typically HTTP 403
     |
     +--> Valid token => continues to filters/authorization
                                |
                                +--> unauthenticated => possibly 401 / redirect
                                +--> insufficient permissions => 403
                                +--> sufficient permissions => enters controller
```

**A valid CSRF token does not automatically log a user in.** A caller can submit a valid CSRF token without authentication; after the CSRF step, the URL can still deny access because login is required. Conversely, an authenticated user sending a POST without a token can still receive 403 **before** reaching the controller.

### 2.2 CSRF RequestPostProcessor in Spring Security Test

Key helpers:

```java
// MockMvc fragment; mvc is a MockMvc integrated with Spring Security.
mvc.perform(post("/api/notes").with(csrf()));                    // valid token as parameter
mvc.perform(post("/api/notes").with(csrf().asHeader()));         // valid token as header
mvc.perform(post("/api/notes").with(csrf().useInvalidToken()));  // invalid token
mvc.perform(post("/api/notes"));                                 // no token supplied
```

`csrf()` resides in `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors`. The helper generates a token suited to the test environment; it **does not** replace testing production token generation, rotation, storage/reading, and real-world JavaScript integration.

**Expected-outcome definitions must include authentication state.** Testing POST with `@WithMockUser` or `.with(user(...))` isolates CSRF testing from anonymous errors. If you omit a user and expect 200 solely because of a CSRF token, the test premise is mistaken.

### 2.3 Mandatory test scenarios

| Test | Authentication | CSRF token | Expected for login-required POST endpoint |
| --- | --- | --- | --- |
| POST with user, no token | Present | Missing | **403**, controller must not execute |
| POST with user, wrong token | Present | Invalid | **403** |
| POST with user, valid token in form parameter | Present | Valid | Proceeds: **200/201** if controller succeeds |
| POST with user, valid token in header | Present | Valid | Proceeds: **200/201** |
| Anonymous POST, valid token | Missing | Valid | **401** with HTTP Basic; may redirect with form login |
| Read-only GET endpoint | Depends on URL | Not needed | Must not be blocked solely for lacking CSRF |

If a POST endpoint is configured with `csrf.ignoringRequestMatchers(...)`, tests must reflect that **intentional decision**; never disable CSRF merely to make tests green. Especially with cookie-based sessions and auto-sent browser credentials, CSRF still demands full evaluation.

## 3. CORS: understanding preflight vs simple/actual requests

### 3.1 What exactly makes up an Origin?

An **origin** is the combination of *scheme + host + port*. `https://portal.example.test` differs from `http://portal.example.test`, differs from `https://api.example.test`, and differs from the same host on another port. CORS is a **cross-origin** policy; never compare only hostnames and grant broad access.

A preflight looks like:

```http
OPTIONS /api/notes HTTP/1.1
Origin: https://portal.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Browsers typically **do not send cookies/sessions** on preflight requests. CORS must run early enough, before authentication filters reject anonymous OPTIONS requests. In Spring Security Servlet, configure `CorsConfigurationSource` and `http.cors(...)`, or integrate Spring MVC's CORS policy appropriately.

When origin/method/headers are permitted, the response may contain:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
```

Actual header lists and ordering depend on configuration and framework version. Tests should assert **essential values** and may use matchers like "contains POST" rather than binding to full string ordering. `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` may also be added so caches distinguish requests; verify this when caches/gateways are in scope.

### 3.2 Preflight vs actual cross-origin requests

- **Preflight:** OPTIONS asks in advance about allowed origin, method, and headers; carries no user credentials or CSRF tokens and does not run POST business logic.
- **Actual request:** the browser's real GET/POST; the CORS filter adds matching `Access-Control-Allow-...` headers to the response and passes the request onward, while authentication/authorization/CSRF remain enforced.
- **Request without Origin:** not a CORS request; the server still enforces authentication/CSRF as usual. Do not blindly expect `Access-Control-Allow-Origin` on every response.

When `allowCredentials=true`, never use the `*` wildcard for `Access-Control-Allow-Origin` with browsers; declare exact origins or carefully designed patterns. Never combine `allowedOriginPatterns("*")` with credentials and accidentally expose API reads to every website.

### 3.3 CORS matrix to test

| Test | Origin | Method | Preflight request headers | Expected |
| --- | --- | --- | --- | --- |
| Allowed preflight | `https://portal.example.test` | POST | content-type, x-csrf-token | 200; matching allow-origin; allow-methods contains POST |
| Preflight wrong origin | `https://evil.example.test` | POST | content-type | 403 or rejected by CORS processor; no trusted allow-origin |
| Preflight method outside whitelist | Valid origin | DELETE | content-type | Not permitted by browser for cross-origin execution |
| Preflight requesting disallowed header | Valid origin | POST | x-secret-admin | Header is not approved |
| Actual GET from allowed origin | Valid origin | GET | Not a preflight | Correct CORS headers **and** authorization still enforced |
| Actual POST allowed origin missing CSRF | Valid origin | POST | No token | Still 403 due to CSRF |
| Same-origin / no-Origin request | None | GET | None | No CORS allow-origin needed |

**Note:** Spring's default CORS processor status on rejection is typically 403, yet the key goal is that the browser receives no header allowing the forbidden origin/method/header. Never rely **solely** on status codes to declare CORS safe.

## 4. Security response headers to verify

Spring Security adds several default headers and allows further customization. Always check values against your **exact version and configuration**; CSP, Referrer-Policy, and Permissions-Policy do not appear automatically just from adding the security starter.

| Header | Meaning | Common expectation |
| --- | --- | --- |
| `X-Content-Type-Options` | Stops browsers from MIME-type sniffing | `nosniff` |
| `X-Frame-Options` | Mitigates certain clickjacking via framing | `DENY` by default; `SAMEORIGIN` optional |
| `Cache-Control` | Reduces caching of sensitive responses | Includes `no-cache` and `no-store` on protected responses |
| `Pragma`, `Expires` | Legacy cache-control compatibility | Often present when default cache-control headers are enabled |
| `Strict-Transport-Security` (HSTS) | Tells browsers to remember HTTPS-only access | Written only on requests treated as **HTTPS** by the app |
| `Content-Security-Policy` (CSP) | Restricts resource/script/iframe origins via directives | **Must be explicitly configured** for the app; do not assume a default |
| `Referrer-Policy` | Limits Referer details sent to other pages | No mandatory universal default; e.g., explicitly set `no-referrer` |
| `Permissions-Policy` | Restricts browser features (camera, location...) | Must be designed and tested separately if used |
| `X-XSS-Protection` | Legacy header for old browser XSS auditors | Not a substitute for CSP/escaping; modern browsers generally ignore it |

### 4.1 HSTS and HTTPS in tests

A regular MockMvc request is treated as plain HTTP. **`Strict-Transport-Security`** is normally **not** added by Spring Security if `request.isSecure()` is false. To test HSTS, use:

```java
mvc.perform(get("/api/public").secure(true))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Strict-Transport-Security", containsString("max-age=")));
```

This is a Java fragment assuming `MockMvc`, `get`, `header`, and `containsString` are imported. `secure(true)` **simulates** HTTPS on the servlet request; it does not test TLS handshakes, certificates, or real proxies. When TLS terminates at a load balancer, the app must configure proxy/Forwarded headers **trusting only real proxy sources**, never trusting an arbitrary client's `X-Forwarded-Proto`.

### 4.2 CSP is an application-specific policy

The example uses `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'` for clear testing. CSP targets browsers and must fit real frontend assets. Pure JSON APIs may not need the same detailed CSP as HTML pages; never copy a demo CSP onto a site using inline scripts or CDNs and treat browser blocks as a Spring security bug.

Both `X-Frame-Options: DENY` and CSP `frame-ancestors 'none'` help restrict framing; response header tests do not prove all clickjacking vectors are blocked in every legacy browser. Test in real browsers when UX requires embedded iframes.

### 4.3 Headers do not replace input/output controls

CSP is an XSS mitigation layer, not a replacement for output encoding, input validation, `Secure`/`HttpOnly`/`SameSite` cookies, role checks, or server-side template reviews. `X-Content-Type-Options: nosniff` does not fix an app returning the wrong MIME type. HSTS means nothing if HTTPS is not deployed securely. Tie test results to your threat model and client behavior.

## 5. Runnable Spring Boot 3.3.5 project — CSRF + CORS + headers

The example intentionally **keeps CSRF enabled**, configures exact CORS for one origin, and uses HTTP Basic to clarify authenticated/anonymous tests. Browsers may send HTTP Basic automatically in some scenarios, so never disable CSRF on an API merely because the route starts with `/api/`.

### 5.1 Structure and dependencies

```text
web-security-defenses/
├── pom.xml
└── src/
    ├── main/java/com/example/defenses/
    │   └── WebSecurityDefensesApplication.java
    └── test/java/com/example/defenses/
        └── WebSecurityDefensesApplicationTest.java
```

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>web-security-defenses</artifactId>
    <version>1.0.0</version>
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
```

### 5.2 Security configuration and controller

Create `src/main/java/com/example/defenses/WebSecurityDefensesApplication.java`:

```java
package com.example.defenses;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class WebSecurityDefensesApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSecurityDefensesApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails tester = User.withUsername("tester")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(tester);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://portal.example.test"));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .cors(Customizer.withDefaults())
            // Intentionally keep CSRF enabled so it can be tested.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; frame-ancestors 'none'"))
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicy.NO_REFERRER)))
            .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/api/profile")
        String profile(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @PostMapping("/api/notes")
        String addNote() {
            return "note created";
        }
    }
}
```

**Configuration explanation:**

1. `.cors(...)` integrates CORS handling into the security chain; `UrlBasedCorsConfigurationSource` defines the **exact** origin `https://portal.example.test`, allowed methods, and allowed request headers. CORS preflight is handled before authentication.
2. `.csrf(...)` keeps CSRF active. There is no `.csrf(...disable)` or `ignoringRequestMatchers` for POST.
3. `/api/public` allows anonymous access; `/api/profile` and `/api/notes` require authentication. Insufficient-role rules can be added in other apps; this demo focuses on CSRF/CORS/headers.
4. `httpBasic` makes 401 clear for anonymous callers; `formLogin` is disabled so tests do not deal with login redirects.
5. Spring Security's default headers remain active. The demo **adds** CSP and Referrer-Policy since these are not mandatory defaults.
6. `allowCredentials(true)` merely tells browsers credentials may accompany requests from the allowed origin; it grants no authentication/roles and does not bypass CSRF.
7. The weak demo password is for learning machines only. Production must apply proper secret policies, password hashing, HTTPS, CSRF token repositories, and CORS origins matching the real frontend.

## 6. Complete MockMvc test suite

Create `src/test/java/com/example/defenses/WebSecurityDefensesApplicationTest.java`. It uses `@SpringBootTest` and `@AutoConfigureMockMvc` to run the real `SecurityFilterChain` in MockMvc, while `@WithMockUser` supplies a simulated identity for specific tests to isolate authentication requirements.

```java
package com.example.defenses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebSecurityDefensesApplicationTest {

    private static final String ALLOWED = "https://portal.example.test";
    private static final String DENIED = "https://evil.example.test";

    @Autowired
    MockMvc mvc;

    // --- CSRF: 4 token states and anonymous ---

    @Test
    @WithMockUser
    void missingCsrfTokenBlocksPost() throws Exception {
        mvc.perform(post("/api/notes"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void invalidCsrfTokenBlocksPost() throws Exception {
        mvc.perform(post("/api/notes").with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void validCsrfParameterAllowsPost() throws Exception {
        mvc.perform(post("/api/notes").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note created"));
    }

    @Test
    @WithMockUser
    void validCsrfHeaderAllowsPost() throws Exception {
        mvc.perform(post("/api/notes").with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(content().string("note created"));
    }

    @Test
    @WithAnonymousUser
    void csrfTokenDoesNotAuthenticateAnonymousUser() throws Exception {
        mvc.perform(post("/api/notes").with(csrf()))
            .andExpect(status().isUnauthorized());
    }

    // --- CORS: preflight without login cookie is still processed ---

    @Test
    void allowedPreflightIsAccepted() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void disallowedMethodPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void disallowedHeaderPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "x-secret-admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser
    void actualCorsGetRetainsAuthenticationRequirement() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isOk())
            .andExpect(content().string("hello user"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    @WithMockUser
    void allowedCorsOriginDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    void requestWithoutOriginDoesNotRequireCorsHeader() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    // --- Default headers and additionally configured headers ---

    @Test
    void defaultSecurityHeadersExist() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL, containsString("no-store")));
    }

    @Test
    void customCspAndReferrerPolicyExist() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; frame-ancestors 'none'"))
            .andExpect(header().string(
                "Referrer-Policy", "no-referrer"));
    }

    @Test
    void hstsAppearsForHttpsRequest() throws Exception {
        mvc.perform(get("/api/public").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=")));
    }

    @Test
    void hstsIsNotAddedForPlainHttp() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }

    // --- Real authentication: do not confuse with @WithMockUser ---

    @Test
    void realHttpBasicCredentialCanReadProfile() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("tester", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello tester"));
    }

    @Test
    void realHttpBasicCredentialDoesNotBypassCsrf() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("tester", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void realHttpBasicCredentialAndCsrfCanPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("tester", "demo123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note created"));
    }
}
```

### 6.1 What is being verified?

The test suite contains **19 cases** across three groups:

- **CSRF (5 cases):** missing token 403, invalid token 403, valid token in parameter/header succeeds, anonymous with CSRF remains unauthenticated.
- **CORS (7 cases):** valid preflight passes without login, bad origin/method/header rejected; actual requests receive allow-origin yet still require authentication/CSRF; requests without Origin need no CORS header.
- **Security headers and real authentication (7 cases):** `nosniff`, `DENY`, `no-store`, CSP, Referrer-Policy, HSTS on HTTPS/HTTP; HTTP Basic with real password; POST still requires CSRF.

The example uses `@WithMockUser` to test the CSRF filter **independently** of login, and `httpBasic(...)` in separate cases to send a Basic header through the demo's real authentication provider/`PasswordEncoder`. With only mock users, a 200 result does not prove the password is valid.

### 6.2 How to run and expected results

Install JDK 17+ and Maven, open a terminal in the project directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

`mvn test` runs the JUnit/MockMvc test suite. The statuses/bodies in the tables are **expectations derived from source**; do not claim tests passed without running them in a real environment.

Additional tests with curl:

```bash
# Public endpoint needs no CSRF token since this is GET:
curl -i http://localhost:8080/api/public

# GET with HTTP Basic credentials:
curl -i -u tester:demo123 http://localhost:8080/api/profile

# POST even with valid credentials still lacks CSRF -> 403:
curl -i -u tester:demo123 -X POST http://localhost:8080/api/notes

# CORS preflight from an allowed origin:
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: https://portal.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

The commands above are for Unix/macOS/Git Bash shells; on Windows PowerShell `curl` may be an alias depending on version, so use `curl.exe`. The plain curl POST does not perform real CSRF token issuance; `MockMvc.with(csrf())` simulated the token for tests.

**Why not make POST "just work with curl"?** Because the lesson's goal is **testing active CSRF protection**; letting every tokenless POST succeed would hide the exact vulnerability we need to prove is blocked. In real applications, the frontend retrieves tokens from an endpoint/HTML/cookie according to `CsrfTokenRepository` and the configured request handler.

## 7. Testing CSRF with real sessions, cookies, or SPAs

Spring Security 6 uses **deferred token loading** and BREACH protection by default; how tokens are exposed to clients and resolved depends on `CsrfTokenRequestHandler`, `CsrfTokenRepository`, and frontend architecture. `csrf()` is convenient for MockMvc yet does not test the full browser token lifecycle.

If the application uses sessions/cookies or a SPA, also verify:

1. **Obtaining the token:** the frontend retrieves the token properly (rendered hidden field, token endpoint, or cookie if architecturally appropriate).
2. **Submitting the token:** POST/PUT/PATCH/DELETE sends the right header/form field; the browser sends the auth cookie per policy.
3. **Missing/wrong token:** rejected even when the browser has a valid session.
4. **Login/logout/session change:** verify whether old tokens remain valid or rotate/clear according to real policy.
5. **SameSite/Secure/HttpOnly:** inspect cookies on **real responses** and browser behavior; `SameSite` is defense-in-depth, not an automatic replacement for CSRF.
6. **Never expose tokens in URLs:** query strings appear in logs, browser history, and Referer headers.
7. **CSRF-exempt routes:** exempt only flows justified by the threat model and test negative paths too; never exempt `/api/**` broadly without proof that clients send no auto-attached credentials.

In stateless apps that accept only Bearer tokens attached manually by JavaScript to `Authorization` and **never** use auto-sent cookies/sessions/HTTP Basic, CSRF risk differs; disabling CSRF must be grounded in how browsers handle credentials and your threat model, while continuing to test CORS and authorization. There is no blanket rule that "REST APIs always disable CSRF."

## 8. Testing CORS in browsers and reverse proxies

### 8.1 What does MockMvc prove, and what does it not?

`MockMvc` runs the app in a servlet test environment and can exercise the CORS filter. It proves the server **emits the right headers** when requests carry `Origin`/preflight headers. However, it **does not enforce the browser's Same-Origin Policy**.

Browser-based E2E tests are needed to verify:
- Whether a frontend on origin A can actually read an API response from origin B in practice.
- `SameSite`, `Secure`, `credentials: "include"`, and authentication redirects.
- Whether a CDN/reverse proxy accidentally injects `Access-Control-Allow-Origin: *`, strips `Vary`, or caches responses under the wrong origin.
- Preflight caching and per-environment policies (dev/staging/production).
- Whether CSP frame/script directives block intended threats without breaking app features.

### 8.2 Do not open CORS to "fix 403"

A 403 can stem from CSRF, authentication, missing permissions, CORS, or an upstream proxy. Before changing anything, check:

1. Does the request carry an `Origin`? Is it genuinely an OPTIONS preflight with `Access-Control-Request-Method`?
2. Which HTTP status and headers came from `CorsFilter`/gateway? Is the browser console reporting a CORS error or did the server reject authorization?
3. Did the POST carry a valid CSRF token per repository/handler?
4. Is the user authenticated and holding the right authority?
5. Do origin scheme/host/port match the whitelist? Is the frontend sending credentials and does policy enable `allowCredentials` properly?
6. Are multiple `SecurityFilterChain`s, `CorsConfigurationSource`s, or proxy header overrides involved?

Never switch `allowedOrigins` to a wildcard to dodge an error. A response carrying the right `Access-Control-Allow-Origin` only proves server CORS configuration—never that the endpoint is safe against CSRF or unauthorized access.

## 9. Testing headers when deploying with HTTPS and a real frontend

### 9.1 Header checks by environment layer

| Verification layer | Specific checks | Tool |
| --- | --- | --- |
| Spring Security filter | `X-Content-Type-Options`, `X-Frame-Options`, cache headers | MockMvc |
| Application customization | CSP, Referrer-Policy, Permissions-Policy if configured | MockMvc |
| HTTPS | HSTS only on HTTPS, HTTP->HTTPS redirects if required | Simulated MockMvc + integration over HTTPS |
| Proxy/CDN | Proxy does not strip/overwrite headers or drop `Vary` | Tests against real deployment |
| Browser | Do CSP violations appear? Are iframes blocked? | Browser devtools/E2E |
| Static files and public data | Does `Cache-Control` fit each endpoint and asset? | Integration/contract tests |

Spring Security sets cache-control headers by default to prevent caching sensitive responses. Yet versioned static assets (e.g., `app.abc123.js`) may need different cache policies. Do not write a rigid test demanding `no-store` for **every URL** without checking resource purpose and overrides. In the demo, `/api/public` still receives default headers because no custom cache policy was set.

### 9.2 HSTS and HTTPS forwarding

HSTS requires real HTTPS for browsers to trust it. Behind a reverse proxy, requests reaching the internal server may be HTTP even though the browser uses HTTPS. Verify trusted forwarded-header configuration and proxy headers, ensuring arbitrary clients cannot spoof the scheme.

Use `.secure(true)` in MockMvc only to test the header writer's condition; add an integration test against the public HTTPS endpoint to verify the environment. Before raising `max-age` or enabling `includeSubDomains` or `preload`, consider the impact across every subdomain; never enable preload casually just to assert the header value in tests.

### 9.3 Headers not added automatically by Spring Security

**CSP, Referrer-Policy, and Permissions-Policy** must be configured explicitly where needed. In the demo, CSP and Referrer-Policy were configured deliberately. Never conclude "Spring Security lacks security" simply because a pure-JSON API omits CSP; decide policy per app. When headers are part of the project's security contract, configure and test them precisely to prevent regressions.

### 9.4 Do not test outdated defaults

`X-XSS-Protection` is a legacy header and may appear disabled or absent depending on version/config. Modern browsers rely primarily on CSP and output encoding. Do not copy expectations from Spring Security 4.x/5.x onto 6.x/7.x; check the docs for your active version.

## 10. Common test-suite mistakes and how to avoid them

### Mistake A — Omitting `csrf()` so POST tests run faster

A POST with a user and no token returning 403 is working by design. Never disable CSRF globally in production config just to pass tests. Separate tests: **POST without token must 403**, **POST with valid token must succeed**.

### Mistake B — Assuming `@WithMockUser` creates a CSRF token

`@WithMockUser` creates a mock identity and does not attach a request CSRF token. Tests should treat authentication and CSRF as **two independent dimensions**. Even with `.with(csrf())`, an anonymous test can still return 401 due to missing authentication.

### Mistake C — Sending CORS preflight with HTTP Basic and calling it browser behavior

Normal browser preflights do not carry session cookies. If Spring Security requires authentication on OPTIONS, the frontend can break even when GET/POST business logic works. Test preflight **unauthenticated**, carrying only `Origin` and `Access-Control-Request-*`.

### Mistake D — Seeing an allowed origin and assuming POST cleared CSRF

CORS governs cross-origin reading; CSRF protects state-changing actions. Test `allowedCorsOriginDoesNotBypassCsrf` proves requests from an allowed origin must still pass CSRF and can receive 403.

### Mistake E — Testing CORS solely with status 200

An OPTIONS response can return 200 yet omit `Access-Control-Allow-Origin` or disallow a required header/method, stopping the browser from sending the actual request. Assert allow-origin, allow-methods, and allow-headers/credentials where relevant; test bad origins and methods on negative paths.

### Mistake F — Using `Access-Control-Allow-Origin: *` with credentials

Browsers reject wildcards on credentialed cross-origin responses. Whitelist specific origins and assert the exact value. Verify no proxy alters headers downstream of Spring Security.

### Mistake G — Treating `Origin` as proof of identity

Non-browser HTTP tools can send any arbitrary `Origin`. Never use the Origin header to grant roles, bypass authentication, or authorize resources. CORS is a browser cross-origin control layer.

### Mistake H — Asserting HSTS on plain HTTP MockMvc

HSTS is added only for secure requests; plain HTTP MockMvc requests will normally omit the header. Test both `.secure(true)` and plain requests. Behind reverse proxies, test proxy/forwarded headers properly.

### Mistake I — Asserting CSP as a default header

Spring Security cannot pick a universal CSP for every website. If a project needs CSP, configure `headers.contentSecurityPolicy(...)` explicitly and test the policy. Overly strict CSPs can also break legitimate resources; verify in a browser.

### Mistake J — Disabling the filter chain in MockMvc

If `@AutoConfigureMockMvc(addFilters = false)` or `MockMvcBuilders.standaloneSetup(controller)` omits Spring Security, tests can return 200 even without CSRF; that is **not proof the endpoint is safe**. Use default `@AutoConfigureMockMvc` or `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())`.

### Mistake K — Testing "right headers" while forgetting negative paths

Asserting only `X-Frame-Options` and CSP will not catch tokenless POSTs slipping through or invalid origins accepted by CORS. Balance **allow cases and deny cases**, covering real URLs and HTTP methods.

### Mistake L — Ignoring the role of proxies/CDNs

Headers can be rewritten by ingress controllers or API gateways. Unit/MockMvc tests confirm the application emits headers, while deployment tests verify responses reaching the browser remain intact.

## 11. QA checklist before merging

1. **CSRF:** verify GET/HEAD do not mutate state; POST/PUT/DELETE test missing/invalid/valid tokens; authentication and CSRF are tested independently.
2. **CORS:** test valid and invalid origins, allowed and disallowed methods/headers, anonymous preflight, actual requests with auth/CSRF; never pair wildcards with credentials.
3. **Default headers:** `nosniff`, frame options, cache-control match version behavior; do not assert obsolete legacy headers.
4. **Custom headers:** CSP, Referrer-Policy, Permissions-Policy if required by system; verify directives and confirm frontend features are unbroken.
5. **HSTS/HTTPS:** test secure requests, do not require HSTS on plain HTTP; with TLS termination, test real proxy behavior.
6. **HTTP security:** 401/403/200 match configuration, never confusing CSRF/CORS errors with role errors. On denial, business handlers must not run.
7. **Test setup:** security filter chain is active; `spring-security-test` is in test dependencies; MockMvc integrates Spring Security.
8. **Real authentication:** when proving passwords/JWT/OAuth2 work, include tests sending real credentials/tokens; `@WithMockUser` only mocks context.
9. **Observability:** logs/metrics never contain CSRF tokens, session cookies, raw Authorization/JWTs, or sensitive data.
10. **Regression:** run browser/E2E tests for CSP, cookies, CORS from frontend origins, gateway headers, and production-like deployments when needed.

## 12. Key takeaways

- **CSRF** prevents browsers from performing unauthorized state-changing actions; test valid, missing, and invalid tokens, and never confuse CSRF tokens with logging in.
- **CORS** is a policy for browsers to govern cross-origin access; preflight must run before authentication, and tests must cover disallowed origins/methods/headers. CORS **does not** replace authentication or CSRF.
- **Security response headers** guide browsers; verify version-appropriate defaults, configured CSP/Referrer policies, and HSTS on HTTPS only.
- **MockMvc** proves Spring Security filters/handlers generate the right responses; it does not simulate full browsers, TLS, proxies, caches, or frontend JavaScript.
- A strong suite pairs **negative cases** (403 on bad CSRF, forbidden preflight, no HSTS on HTTP) with **positive cases** (valid CSRF, allowed origin, complete headers on HTTPS).
- Never disable filters or open wildcards to "make tests green"; fix the root cause and keep defenses under test.

## Official reference documentation

- Spring Security — Servlet CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — CORS for Servlet Applications: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Security HTTP Response Headers (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security — MockMvc Testing Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — Setup MockMvc with Spring Security: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Framework — CORS: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — Reactive CSRF (for WebFlux comparison): https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html