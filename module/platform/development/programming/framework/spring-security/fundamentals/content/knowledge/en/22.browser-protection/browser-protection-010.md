# Customizing default browser protections for specific needs and test criteria

## 1. Understand the problem before changing configuration

Spring Security provides several defense layers for **web applications running in browsers**. Browsers automatically send session cookies, parse HTML/JavaScript, enforce CORS policies, and act on HTTP response headers. Consequently, a change that seems meant merely to "make the UI work" (allowing iframes, relaxing CORS, turning off CSRF, enabling caching) can weaken attack resistance.

For example, an order-management app hosts its UI and API on the same origin using cookie-based sessions. A `POST /orders` form requires a CSRF token. When splitting the frontend onto a different origin, the team must also design CORS and a CSRF token exchange mechanism; enabling CORS **does not replace** CSRF verification.

**Principle:** start from safe defaults; customize only when backed by a concrete requirement defined by **browser flows, risks, and test criteria**. This lesson uses Spring Security **Servlet** (`HttpSecurity` / `SecurityFilterChain`, suited for Spring Boot 3.x and Spring Security 6.x). For WebFlux, use `ServerHttpSecurity` and its reactive test tools instead of copying Servlet config verbatim.

## 2. Defaults to recognize

| Mechanism | Typical Spring Security Servlet behavior | When to consider customizing? |
| --- | --- | --- |
| CSRF | Protects state-changing methods like `POST`, `PUT`, `PATCH`, `DELETE` by default; safe methods like `GET` do not require a token. | SPAs using cookies, webhook endpoints with independent signature verification, or multiple login flows. |
| `X-Frame-Options` | `DENY`, preventing pages from being embedded via `iframe`. | A page genuinely needs same-origin embedding; clickjacking risk must be evaluated. |
| `X-Content-Type-Options` | `nosniff`, discouraging MIME type sniffing. | Almost always keep enabled; fix wrong resource `Content-Type` instead of disabling `nosniff`. |
| `Cache-Control`, `Pragma`, `Expires` | Restricts caching of sensitive responses by default. | Allow appropriate caching only for static, public resources; keep strict policies on personal-data pages. |
| `Strict-Transport-Security` (HSTS) | Added to **HTTPS responses**, does not appear on plain HTTP. | Systems behind reverse proxies, subdomain scope, HTTPS/HSTS rollout strategy per environment. |
| `X-XSS-Protection` | Defaults to `0` because legacy browser XSS filters are obsolete. | Never try enabling legacy filters in place of output encoding and CSP. |
| Content Security Policy (CSP) | **Not added automatically by Spring Security.** | When restricting script, style, object, and framing sources. |
| `Referrer-Policy` | **Not added automatically by Spring Security.** | When limiting URL details sent in the `Referer` header. |
| CORS | Allowed origins and methods must be declared when UI calls cross-origin APIs. | SPA on a different domain/port; never use CORS as authentication or a CSRF replacement. |

Beyond these headers, cookie attributes like `Secure`, `HttpOnly`, and `SameSite` are typically governed by cookie/session configuration and HTTP infrastructure rather than `HttpSecurity.headers(...)` alone. `SameSite=Lax` helps, yet is never a reason to drop CSRF for apps using auto-sent cookie authentication.

Distinguish three questions: **Who may send the request?** (authentication, authorization), **may the browser read a cross-origin response?** (CORS), and **was a state-changing request intentionally initiated by a legitimate UI?** (CSRF). Each addresses a different threat.

## 3. Choosing configurations by real-world scenario

| Context | Appropriate decision | What to verify |
| --- | --- | --- |
| Same-origin Web MVC / Thymeleaf with session cookie login | Keep CSRF; include tokens in forms; keep `X-Frame-Options: DENY` and `nosniff`; add tailored CSP. | Valid forms succeed, POSTs missing/invalid CSRF tokens are rejected, pages cannot be framed unexpectedly. |
| Cross-origin SPA calling API with session cookies | Allow only specific origins, enable credentials as needed; keep CSRF and design how the SPA obtains/sends tokens. | Valid preflights succeed; unknown origins are denied CORS; write requests missing tokens remain blocked. |
| API strictly using client-attached bearer tokens, no cookies/HTTP Basic or auto-sent credentials | Evaluate CSRF per endpoint and browser usage; **narrowly scoped** exclusions may apply after verifying the auth model. | No browser path auto-attaches credentials to mutate state; authorization still holds. |
| Report page needing display inside a same-origin `iframe` | Switch to `SAMEORIGIN` and CSP `frame-ancestors 'self'` strictly for the embeddable scope. | Same-origin embedding works; external origins remain blocked. |
| Public CSS/JS assets needing caching | Configure dedicated caching for static assets while keeping personal-data pages protected. | Static responses carry expected cache policies; account pages remain non-cacheable. |

Never disable all security protections just to silence a `403` error or CORS warning. First identify which step blocked the request, gather evidence from Network/Console/logs, and pinpoint which rule actually needs adjustment.

## 4. Runnable Java example: keep CSRF, add CSP and Referrer-Policy

Assume a **Spring Boot 3.x, Java 17+** project with `spring-boot-starter-web` and `spring-boot-starter-security`, plus `spring-boot-starter-test` and `spring-security-test` in test scope. These are dependencies for a Boot project with a full build setup (not a plain Java file runnable via `javac` alone).

`build.gradle` snippet (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`src/main/java/demo/browser/BrowserSecurityApplication.java`:

```java
package demo.browser;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrowserSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrowserSecurityApplication.class, args);
    }
}
```

`src/main/java/demo/browser/SecurityConfig.java`:

```java
package demo.browser;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                // Permit two demo endpoints to isolate CSRF testing.
                .requestMatchers("/demo/**").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; object-src 'none'; " +
                    "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
                ))
                .referrerPolicy(referrer -> referrer.policy(
                    ReferrerPolicyHeaderWriter.ReferrerPolicy
                        .STRICT_ORIGIN_WHEN_CROSS_ORIGIN
                ))
            );
        return http.build();
    }
}
```

`src/main/java/demo/browser/DemoController.java`:

```java
package demo.browser;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class DemoController {
    @GetMapping("/state")
    public String readState() {
        return "ok";
    }

    @PostMapping("/state")
    public String updateState() {
        return "updated";
    }
}
```

**Behavior explanation:**

- `.csrf(Customizer.withDefaults())` preserves default CSRF protection. `permitAll()` on `/demo/**` waives only the *login* requirement for this demo; it **does not bypass the CSRF filter**.
- The illustrative CSP loads resources only from the same origin, disallows `object`, restricts base URL changes, prevents cross-origin framing, and restricts form submission targets. Real pages using inline scripts, CDNs, or external images must inventory assets and tailor CSP accordingly rather than adding `'unsafe-inline'` indiscriminately.
- `Referrer-Policy: strict-origin-when-cross-origin` limits URL data sent to other origins. It does not replace keeping secrets out of URLs.
- Default headers such as `X-Frame-Options: DENY` and `X-Content-Type-Options: nosniff` remain active when only these two headers are added.
- Demo endpoints return simple strings publicly **solely to observe browser defense layers**. In production, enforce real access control before release.

## 5. Automated testing: both permitted and rejected cases

Create `src/test/java/demo/browser/BrowserSecurityTests.java`:

```java
package demo.browser;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BrowserSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void httpResponseHasDefaultAndCustomHeaders() throws Exception {
        mockMvc.perform(get("/demo/state"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; object-src 'none'; " +
                "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
            ))
            .andExpect(header().string(
                "Referrer-Policy", "strict-origin-when-cross-origin"
            ))
            .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }

    @Test
    void httpsResponseContainsHsts() throws Exception {
        mockMvc.perform(get("/demo/state").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().exists("Strict-Transport-Security"));
    }

    @Test
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/demo/state"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidCsrfTokenIsAccepted() throws Exception {
        mockMvc.perform(post("/demo/state").with(csrf()))
            .andExpect(status().isOk());
    }
}
```

Run from the Gradle Boot project root with wrapper:

```bash
./gradlew test --tests demo.browser.BrowserSecurityTests
```

Each of the four tests verifies a distinct behavior: checking default and added headers; proving HSTS appears only when a request is recognized as HTTPS; proving state-changing requests **without a CSRF token** are blocked with `403`; and proving requests with a valid token return `200`. The test helper `with(csrf())` generates a valid token for MockMvc; it **does not prove** that SPA JavaScript properly retrieves and attaches the token. These tests simulate Servlet requests rather than full real-browser behavior.

You can also inspect running responses with:

```bash
curl -i http://localhost:8080/demo/state
```

`curl` displays HTTP headers yet does not enforce framing, CSP, or CORS rules like a browser. To verify those behaviors, inspect Network, Console, and UI flows in a real browser.

## 6. Three common customizations needing dedicated tests

### 6.1. Cross-origin SPA calling an API with session cookies

Enable CORS only when genuinely required. With a frontend at `https://app.example.com` and a backend API on another origin, add this **configuration snippet** to your Spring Security config class (importing from `org.springframework.web.cors` and `java.util.List`):

```java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    config.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
    ));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

In `securityFilterChain`, add `http.cors(Customizer.withDefaults())` and keep CSRF enabled for cookie-authenticated write endpoints. Spring Security must handle CORS preflights before requiring authentication, because `OPTIONS` preflight requests typically carry no session cookies. `allowCredentials(true)` must be paired with explicit origins—never `"*"` in `allowedOrigins`. `example.com` is a placeholder; replace it before deploying.

**CORS does not supply CSRF tokens.** Cookie-based SPAs need a flow to obtain tokens, send them in the appropriate header, and refresh them after login/logout. Spring Security 6 provides deferred tokens and BREACH token masking; merely exposing a token cookie to JavaScript can be **insufficient** for the entire SPA flow. Test thoroughly with real browsers, token issuance, and the chosen token handler. Drop `HttpOnly` only on a dedicated CSRF token cookie when architecture explicitly requires JS to read it—never on the session authentication cookie.

Minimum checks: `OPTIONS` from an allowed origin receives exact `Access-Control-Allow-Origin` and permitted methods/headers; unknown origins are not granted access; `POST` without a CSRF token stays blocked; `POST` with a valid token and session cookie succeeds. Never conclude "CORS is secure" merely because the frontend stopped throwing errors.

### 6.2. Embedding part of the UI via iframe

By default `X-Frame-Options: DENY` blocks framing. If one internal report needs same-origin embedding, consider `SAMEORIGIN` and CSP `frame-ancestors 'self'`. Example **customization snippet replacing** the previous example's frame policy:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame.sameOrigin())
    .contentSecurityPolicy(csp -> csp.policyDirectives(
        "default-src 'self'; object-src 'none'; frame-ancestors 'self'"
    ))
)
```

`frame-ancestors` governs **who may embed your page**, unlike `frame-src` which governs **where your page may load embedded frames from**. If only one route needs embedding, scope the policy per route/filter chain or specialized header writer instead of relaxing the entire application. Verify in a browser that same-origin embedding **works** and cross-origin embedding **is blocked**, rather than checking only header strings.

### 6.3. An endpoint not using browser auto-sent authentication

A webhook verified by its own HMAC signature is an example where a narrow CSRF exception may apply. After confirming the endpoint neither uses session cookies nor browser auto-sent credentials, consider:

```java
// Snippet placed in the application's HttpSecurity configuration.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/hooks/provider/**")
);
```

This is **not** a way to turn off webhook authentication: the server must still verify signatures, timestamps, replay protection, and authorization. Notably, calling an API "stateless" is not enough to prove CSRF immunity: JWT cookies and HTTP Basic can still be sent automatically by browsers. Avoid `csrf.disable()` across the whole app just to make one path work.

## 7. Test criteria matrix when changing policies

| Test | Expected result | Appropriate verification method |
| --- | --- | --- |
| `GET` over HTTP | `nosniff`, `DENY`, and configured CSP present; no HSTS if request is HTTP. | MockMvc + header checks. |
| `GET` over HTTPS | HSTS and other defense headers present. | MockMvc `secure(true)`; verify on real HTTPS too. |
| `POST` using cookie, missing/invalid CSRF token | `403 Forbidden`. | Negative MockMvc test; real UI request. |
| `POST` with valid token and proper role | Succeeds per API contract. | Positive MockMvc test; real browser. |
| CORS preflight from allowed origin | Permits only required origins, methods, headers. | Inspect `OPTIONS` and response headers. |
| CORS from disallowed origin | Denied permission to read response via CORS. | Browser DevTools; preflight tests. |
| Page embedded by external origin | Rejected by browser per `X-Frame-Options`/`frame-ancestors`. | Test page with an iframe on an external origin. |
| Page with required scripts/styles | No unexpected CSP errors without resorting to reckless relaxation. | Browser Console, browser automation. |
| Page with session data after logout | No sensitive data exposed from cache. | Inspect response headers, back-navigation, storage/cache. |

When HTTPS goes through a reverse proxy or load balancer, confirm the app observes accurate HTTPS metadata (e.g., trusted forwarded headers configuration); if requests appear as plain HTTP, HTTPS-only HSTS rules will misfire. Before enabling `includeSubDomains` or long-lived HSTS, verify every subdomain supports working HTTPS, since browsers remember the policy for a long time.

Roll out CSP cautiously per resource and route, optionally starting with `Content-Security-Policy-Report-Only` to observe violations before enforcing. Violation reports and header assertions do not replace testing login, forms, iframes, CSS/JS loading, and checkout flows in a real browser.

## 8. Common mistakes and self-review questions

1. **Dropping CSRF because an API uses JSON or is "stateless".** Check whether browsers automatically attach credentials instead of guessing from payload or session style.
2. **Setting `allowedOrigins("*")` with `allowCredentials(true)`.** Specify exact origins and restrict methods/headers to what is needed.
3. **Disabling `X-Frame-Options` globally to fix one iframe.** Relax only the specific pages needing framing and pair with CSP `frame-ancestors`.
4. **Turning on a super-strict CSP without auditing page assets.** Verify scripts, styles, fonts, images, connections, and forms; prefer nonces/hashes or minimal trusted sources over broad wildcards.
5. **Enabling caching on every response for speed.** Cache only suitable public assets; evaluate personal-data pages separately.
6. **Testing HSTS over plain HTTP and thinking it is disabled.** Default HSTS is emitted only on HTTPS responses.
7. **Writing only "happy path works" tests.** Add negative tests for missing/wrong tokens, disallowed origins, external iframes, and CSP-blocked resources.
8. **Confusing `permitAll()` with skipping all filters.** Endpoints may allow anonymous access while still enforcing CSRF, CORS, and security headers.

Before approving any change, verify you can answer: **(a)** what is the exact browser requirement; **(b)** which defaults are kept or altered; **(c)** which endpoints and origins are impacted; **(d)** which tests prove both allowed and denied cases; and **(e)** whether real browsers were tested after deployment.

## References

- Spring Security — [Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html).
- Spring Security — [Cross-Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- Spring Security — [CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/).