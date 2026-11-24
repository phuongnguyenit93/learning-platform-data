# `allowedOriginPatterns` and Controlling the Trusted Origin Set

## 1. Understanding the Right Goal

In a **Spring Security Servlet + Spring MVC** application, `CorsConfiguration#setAllowedOriginPatterns(...)` declares the **Origin patterns permitted to read cross-origin responses in the browser**. This API is useful when multiple valid origins follow a domain naming convention, such as `https://<tenant>.tenant.example.com`, yet great care is required: the `*` character can widen the permitted origin set beyond what you intended.

Core facts:

- **Origin** consists of `scheme + host + port` (for example `https://app.example.com:8443`), excluding path, query, and fragment. `https://app.example.com` and `http://app.example.com` are two different origins; a different port also makes a different origin.
- **CORS is a browser-enforced mechanism** controlling whether JavaScript at one origin can read responses from another origin. Do not treat `Origin` as a trustworthy caller identity: HTTP tools, other backends, or scripts can explicitly set this header.
- **CORS does not replace authentication, authorization, or CSRF protection**. Allowing an origin does not mean authorizing every user on that origin. Conversely, disallowing an origin does not necessarily stop the server from receiving every kind of request.
- `allowedOriginPatterns` is a **pattern-based allowlist**, not an arbitrary regular expression or URL routing config. In systems with cookie-based login, allow only **origins genuinely controlled by the organization**.

**Practical goal:** a main UI `https://app.example.com`, tenant UIs under a managed domain `https://*.tenant.example.com`, and a development environment `http://localhost:5173` can call `/api/**`; websites outside this set must not receive CORS headers permitting data reading.

## 2. CORS Flow and Spring Security's Position

Suppose a page at `https://acme.tenant.example.com` calls the API `https://api.example.com/api/check`.

```text
JavaScript in browser
    |
    | Origin: https://acme.tenant.example.com
    | (may include OPTIONS preflight)
    v
Servlet container
    |
    v
Spring Security FilterChainProxy
    |
    +--> CorsFilter / CORS processing (when http.cors is enabled)
    |        checks Origin, method, request headers
    |        responds to preflight or adds CORS headers
    |
    +--> authentication / authorization filters
    |
    v
DispatcherServlet -> Controller -> JSON response
    |
    v
Browser checks Access-Control-Allow-* headers
    |
    +--> allows JavaScript to read response if valid
    +--> blocks JavaScript from reading response if invalid
```

Preflight usually occurs when the browser wants to use a method or request header outside the preflight-exempt group, for example `Authorization`. The browser sends:

```http
OPTIONS /api/check HTTP/1.1
Host: api.example.com
Origin: https://acme.tenant.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

The server must evaluate **Origin** along with the **actual request's method** (`GET` in `Access-Control-Request-Method`) and requested headers. You do not need to add `OPTIONS` to `allowedMethods` just to permit a preflight for `GET`: `allowedMethods` describes the actual methods to be accepted.

A valid preflight response may contain:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://acme.tenant.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Header order, casing, and combining may vary depending on the servlet container and Spring. With preflight handled successfully right at the CORS filter, the request does not need to enter the controller or go through endpoint login. This is why Spring Security recommends processing CORS **before authentication**: preflight normally carries no session info to authenticate.

## 3. How Does `allowedOrigins` Differ from `allowedOriginPatterns`?

Both settings describe allowed origins, yet their matching behavior and response values differ.

| API | Meaning | When to use |
| --- | --- | --- |
| `setAllowedOrigins(List.of("https://app.example.com"))` | Exact origin list | Default choice for known frontends |
| `setAllowedOrigins(List.of("*"))` | Accepts any origin, usually responds with wildcard `*` | Consider only for public resources; never use with `allowCredentials(true)` |
| `setAllowedOriginPatterns(List.of("https://*.tenant.example.com"))` | Accepts origins matching pattern | Only when all matching subdomains are sufficiently trusted |
| `setAllowedOriginPatterns(List.of("*"))` | Can match any origin and echo the incoming origin | **Dangerous**, especially with `allowCredentials(true)` |

With `allowedOriginPatterns`, if an origin matches, Spring uses the **concrete Origin value** as `Access-Control-Allow-Origin`, for example:

```http
Origin: https://acme.tenant.example.com
Access-Control-Allow-Origin: https://acme.tenant.example.com
```

Instead of:

```http
Access-Control-Allow-Origin: *
```

Therefore patterns can be used when `allowCredentials(true)`. That is only a technical capability—**it does not prove the pattern is safe**. For instance, `allowedOriginPatterns("*")` plus `allowCredentials(true)` can grant cookie-backed response reading permission to countless untrusted websites if cookie and browser conditions permit. Meanwhile, `allowedOrigins("*")` combined with `allowCredentials(true)` is an invalid configuration under Spring's validation.

**Selection rule:** use exact origins when hostnames are known; only add narrow patterns when the problem genuinely requires wildcards and you control the entire corresponding namespace.

## 4. Pattern Syntax and Boundaries That Must Be Controlled

Spring Framework supports `*` in origin patterns and port lists like `:[...]`. Example:

```java
// Illustrative expressions for CorsConfiguration#setAllowedOriginPatterns:
List.of(
    "https://*.tenant.example.com",
    "https://preview.example.com:[8443,9443]",
    "https://*.dev.example.com:[*]"
);
```

- `https://*.tenant.example.com`: only patterns with the HTTPS scheme and matching hostname suffix; `*` can match multiple characters, including dots across sub-levels.
- `https://preview.example.com:[8443,9443]`: illustrates how to list acceptable ports.
- `:[*]`: permits multiple ports, increasing the trust surface; use only when truly needed.
- `https://*.example.com/api` **is not how to configure paths**. Browsers send `Origin` without `/api`; restrict API paths with `registerCorsConfiguration("/api/**", ...)`.
- `https://*.example.com` does not automatically include `https://example.com`. If the root domain is needed, declare it separately.
- Avoid overly broad patterns like `*`, `https://*`, or `https://*example.com`: they can grant access to unintended origins.
- Avoid allowing `Origin: null` unless there is a specific reason and separate assessment. Opaque origins (such as certain sandboxed iframes or `file:` documents) can emit this value.

Consider the following illustrative policy: exact origins `https://app.example.com` and `http://localhost:5173`; pattern `https://*.tenant.example.com`.

| Incoming Origin | Expected outcome | Explanation |
| --- | --- | --- |
| `https://app.example.com` | Allowed | Present in the exact list |
| `http://localhost:5173` | Allowed in dev environment | Dev origin explicitly declared |
| `https://acme.tenant.example.com` | Allowed | Matches pattern |
| `https://a.b.tenant.example.com` | May match | Wildcard does not automatically restrict to one subdomain level; domain policy must be considered |
| `https://tenant.example.com` | Disallowed | Missing subdomain part before `.tenant` |
| `http://acme.tenant.example.com` | Disallowed | Wrong scheme |
| `https://acme.tenant.example.com:8443` | Disallowed | Port not declared in the pattern above |
| `https://acme.tenant.example.com.attacker.test` | Disallowed | Hostname does not end with the permitted suffix |
| `https://attacker.example.net` | Disallowed | Outside allowlist |
| `null` | Disallowed | Not configured |

The table assumes origins are serialized by browsers in standard form. Do not write your own `endsWith("example.com")` check: `https://notexample.com` could also slip past a naive suffix check. When per-tenant control is needed, use verified hostnames and a registered origin list.

## 5. Spring Boot 3.3.x, Spring Security Servlet, and Java 17+ Example

This standalone example uses a `UrlBasedCorsConfigurationSource` dedicated to `/api/**`; Spring Security integrates via `http.cors(Customizer.withDefaults())`. It assumes the organization genuinely manages all permitted hostnames under `tenant.example.com`. If tenants can choose arbitrary domains or create subdomains running untrusted code, **do not use this wildcard as a trust criterion**.

Initialize a Gradle project with Java 17+, Spring Boot Web, and Spring Security; sample `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create `src/main/java/demo/cors/CorsPatternsApplication.java`:

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsPatternsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsPatternsApplication.class, args);
    }
}
```

Create `src/main/java/demo/cors/SecurityConfig.java`:

```java
package demo.cors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/check").permitAll()
                        .anyRequest().authenticated())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Fixed origins: production frontend and local frontend.
        // localhost should only appear in a development configuration profile.
        cors.setAllowedOrigins(List.of(
                "https://app.example.com",
                "http://localhost:5173"));

        // Valid only if all these subdomains are managed by us.
        cors.setAllowedOriginPatterns(List.of(
                "https://*.tenant.example.com"));

        // Demo API scope allows only GET.
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Request-ID"));
        cors.setExposedHeaders(List.of("X-Request-ID"));

        // For the cookie/session example; enable only when genuinely needed.
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
```

Create `src/main/java/demo/cors/DemoController.java`:

```java
package demo.cors;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {
    @GetMapping("/check")
    public ResponseEntity<Map<String, String>> check() {
        return ResponseEntity.ok()
                .header("X-Request-ID", "demo-001")
                .body(Map.of("result", "ok"));
    }
}
```

**Configuration explanation:**

1. `http.cors(Customizer.withDefaults())` activates CORS integration before Spring Security's usual authentication steps. The `UrlBasedCorsConfigurationSource` bean supplies the required policy; no manual `CorsFilter` registration is needed for this example.
2. `setAllowedOrigins(...)` is for the two fixed origins. `http://localhost:5173` is for development; production should separate profiles to remove this origin.
3. `setAllowedOriginPatterns(...)` expands only for HTTPS-matching tenant subdomains. Spring returns the actual matched origin, even when `allowCredentials(true)`.
4. `registerCorsConfiguration("/api/**", cors)` restricts the **API paths where CORS applies**; this is separate from `Origin` matching.
5. `setAllowedMethods(List.of("GET"))` specifies actual request methods allowed via CORS. It does not open `POST`, nor does it alter Spring Security's authorization decisions.
6. `setAllowedHeaders(...)` restricts headers a preflight can request permission to use; `setExposedHeaders(...)` tells the browser to let JavaScript also read the `X-Request-ID` response header.
7. `setMaxAge(1800L)` lets the browser cache the preflight result for the advertised duration, under the browser's own limits and policies.
8. `allowCredentials(true)` is needed only when the frontend is expected to use credentials in cross-origin requests. When cookies are unnecessary, prefer leaving this mode off. This setting does not create cookies or allow cookies to bypass browser `SameSite` or `Secure` rules.
9. The `.permitAll()` rule for GET `/api/check` is **only to test CORS independently of login**. Real endpoints require proper business authorization and can still return `401`/`403` even when CORS is valid.

## 6. Testing Requests and Reading Results Correctly

Start the application using the project's Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows, use `.\gradlew.bat bootRun`. If no wrapper exists yet, generate one with a Gradle version compatible with the Spring Boot version in use.

### 6.1. Preflight from a Valid Tenant

```bash
curl -i -X OPTIONS "http://localhost:8080/api/check" \
  -H "Origin: https://acme.tenant.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
```

With the configuration above, the expected response is HTTP 2xx with values equivalent to:

```http
Access-Control-Allow-Origin: https://acme.tenant.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: Authorization
```

Header values may vary in casing or formatting. What needs confirmation is that the **concrete origin is echoed** and the method/header are allowed. Do not expect `Access-Control-Allow-Origin: *`.

### 6.2. Untrusted Origin

```bash
curl -i -X OPTIONS "http://localhost:8080/api/check" \
  -H "Origin: https://attacker.example.net" \
  -H "Access-Control-Request-Method: GET"
```

With the default CORS processor in the example, an unmatched preflight is typically rejected with HTTP `403` (possibly with body `Invalid CORS request`). More importantly, the response **has no `Access-Control-Allow-Origin` header** granting permission to the attacker. In applications with custom error handling, proxies, or additional filters, exact body/status details may differ; inspect the actual headers.

### 6.3. Actual GET from a Valid Origin

```bash
curl -i "http://localhost:8080/api/check" \
  -H "Origin: https://app.example.com"
```

Expected response:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID
X-Request-ID: demo-001
Content-Type: application/json
```

JSON body equivalent to `{"result":"ok"}`.

`curl` **does not enforce CORS like a browser**: it displays the HTTP result even for rejected origins. Use `curl` to inspect server headers/status, then verify with browser devtools if you need to confirm whether JavaScript can actually read the response.

## 7. Automated Testing of CORS Policy

Create `src/test/java/demo/cors/CorsPatternsIntegrationTest.java`:

```java
package demo.cors;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CorsPatternsIntegrationTest {
    @Autowired
    private TestRestTemplate client;

    private ResponseEntity<String> preflight(String origin) {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin(origin);
        headers.setAccessControlRequestMethod(HttpMethod.GET);
        headers.setAccessControlRequestHeaders(List.of("Authorization"));

        return client.exchange(
                "/api/check",
                HttpMethod.OPTIONS,
                new HttpEntity<Void>(headers),
                String.class);
    }

    @Test
    void trustedTenantPatternReflectsConcreteOrigin() {
        ResponseEntity<String> response =
                preflight("https://acme.tenant.example.com");

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isEqualTo("https://acme.tenant.example.com");
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS))
                .isEqualTo("true");
    }

    @Test
    void untrustedOriginCannotPassPreflight() {
        ResponseEntity<String> response =
                preflight("https://attacker.example.net");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isNull();
    }

    @Test
    void exactAllowedOriginWorksForRealGet() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://app.example.com");

        ResponseEntity<String> response = client.exchange(
                "/api/check",
                HttpMethod.GET,
                new HttpEntity<Void>(headers),
                String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody()).contains("\"result\":\"ok\"");
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isEqualTo("https://app.example.com");
    }
}
```

Run:

```bash
./gradlew test
```

On Windows, use `.\gradlew.bat test`.

Testing with a random port and a real Servlet server lets you observe the CORS filter together with the security filter chain. If the system has a gateway, CDN, multiple `SecurityFilterChain` beans, or environment-specific CORS configs, add end-to-end tests along the real deployment path.

**Expanding negative tests:** `Origin: null`, wrong scheme (`http://`), wrong port, lookalike hostname, unlisted root origin, disallowed method, out-of-set request header, and revoked tenant domain. Negative tests prove the boundaries of the pattern, not just that valid patterns are accepted.

## 8. Designing a Safe Allowlist for Multi-Tenant Systems

A seemingly simple decision like `https://*.tenant.example.com` actually grants permission to **every hostname matching the pattern**, including new subdomains created in the future. Audit domain ownership policy before using it:

- If **the system itself controls DNS provisioning, routing, and content** of all subdomains under `tenant.example.com`, a pattern may be suitable.
- If tenants can **publish untrusted JavaScript, point CNAMEs themselves, create arbitrary subdomains**, or if a previously revoked subdomain can still be taken over, a wildcard can let an untrusted origin read resources of logged-in users.
- For custom domains (such as `https://portal.customer-a.com`), store a **verified list of exact origins** per tenant; do not open a pattern covering broad customer domains.
- When a tenant is deactivated or changes domains, remove the origin from the allowlist and account for the fact that browsers may have cached preflight per `Access-Control-Max-Age`.

A practical origin governance workflow:

1. **Registration:** tenant owner declares the full origin (`https://...`), not just hostname.
2. **Verification:** verify domain/host control per product workflow; never immediately trust the `Origin` string sent by a request.
3. **Approval:** add the origin only to the config for the environment and API services that truly need access; manage auditing and list modification permissions.
4. **Review:** restrict HTTPS, ports, API scope, and cookie rights; detect orphaned subdomains or dangling DNS records.
5. **Revocation:** remove the origin when the tenant loses access or transfers the domain; re-run negative tests.

If dynamic configuration is needed, `CorsConfigurationSource` can determine the per-request policy based on **trusted tenant metadata** and a stored allowlist. Never write logic like "take any `Origin` and echo that same value back", because that is merely a dynamic version of `allowedOriginPatterns("*")`. If using hostname/headers via a reverse proxy to resolve tenants, trust only forwarded headers supplied by a trusted proxy configured to handle them safely.

## 9. Credentials, Cookies, CSRF, and CORS Are Four Different Concepts

When the frontend needs to send cookies/sessions from another origin:

```javascript
fetch("https://api.example.com/api/check", {
  method: "GET",
  credentials: "include"
}).then(response => response.json());
```

For the browser to let JavaScript read a credentialed response, among other conditions, the server must return a **concrete origin** and `Access-Control-Allow-Credentials: true`. However:

- `credentials: "include"` on the frontend does not guarantee cookies are actually sent; the browser also checks domain/path, `SameSite`, `Secure`, third-party cookie policy, and user settings.
- Login cookies must still be bound to an **authenticated user/session**, and every endpoint must still check authorization.
- CORS is not a CSRF token. For requests with cookies, maintain CSRF protection appropriate for the application. The Security config example above does not disable CSRF; state-changing methods such as POST/PUT/DELETE still need proper design.
- `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` **do not prove the caller is legitimate**; `Origin` can be forged by non-browser clients.
- `Access-Control-Allow-Headers: Authorization` only tells the browser it may send that header; it does not authenticate or validate the token. Authentication filters must validate the token themselves.
- If the content is truly public, credentials may not be needed and a simpler CORS config can be used, provided the response contains no private data.

Do not use a broad wildcard plus credentials just because Spring permits patterns; evaluate **which origins can run JavaScript** and **which users have cookies/tokens sent by the browser to the API**.

## 10. Caching, Reverse Proxies, and Multiple Configuration Layers

With dynamic allowlists or patterns, the server may return a different `Access-Control-Allow-Origin` depending on the request. Shared caches/CDNs must distinguish variants by `Origin`. Spring's CORS processor usually adds `Vary: Origin` along with related preflight headers; do not let a gateway strip or overwrite `Vary`.

Common configuration sources:

- A `CorsConfigurationSource` bean used with `http.cors(...)` in Spring Security;
- Spring MVC CORS configuration via `WebMvcConfigurer#addCorsMappings(...)`;
- `@CrossOrigin` on controllers/handlers;
- Manually registered Servlet `CorsFilter`;
- Gateway, ingress, or CDN adding or modifying headers.

These layers can interact in specific ways, yet adding all of them "just to be safe" often results in responses with multiple `Access-Control-Allow-Origin` headers or inconsistent policies. Choose **one primary owner** for the API, understand how Security obtains its config, and test against actual responses. With multiple `SecurityFilterChain` beans or servlet paths, verify which filter chain applies to the target endpoint.

Do not enable `permitAll()` on all endpoints just to make preflight pass. Integrating CORS before authentication is the right direction; authorization of the actual request must remain intact.

## 11. Diagnostic Checklist and Common Errors

| Symptom | Cause to check | Remedy |
| --- | --- | --- |
| Preflight returns `401` or redirects to login | CORS processed after authentication or not integrated into Security | Configure `http.cors(...)` with the proper `CorsConfigurationSource` |
| Server logs `Invalid CORS request` | Requested origin, method, or header does not match | Check the three values: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` |
| `Access-Control-Allow-Origin` missing | Origin not in allowlist, path misses `/api/**`, or proxy alters header | Inspect actual request, path-based config, and final response |
| `Access-Control-Allow-Origin: *` while frontend uses cookies | Wildcard config incompatible with credentialed response | Use exact origins/narrow allowlist; enable credentials only when genuinely needed |
| `allowedOriginPatterns` appears not to apply | Declared `allowedOrigins` by mistake, different bean/source, or multiple filter chains | Inspect the actual configuration object used for the request |
| `https://app.example.com` works, another port fails | Port is part of the origin | Add only the exact approved port |
| Backend returns `200` yet browser reports CORS error | `200` does not prove CORS headers are right | Inspect preflight/actual headers and messages in devtools |
| CORS valid yet API still returns `403` | Authorization or CSRF rejected the actual request | Check Security logs, principal, token/CSRF; do not loosen origins blindly |
| Each environment has a different whitelist | Localhost/staging/prod mixed into one policy | Separate configs/profiles; control deployed origins |
| Cached response contains another request's origin | Cache/proxy does not vary by `Origin` | Preserve `Vary` and verify cache policy |

Specifically: the browser can send a **simple request** before deciding to block JavaScript from reading the response. Therefore protecting server data and behavior still relies on authentication, authorization, CSRF, input validation, and endpoint design; do not rely on the browser throwing a CORS error.

## 12. Comprehension Check Exercises

**Exercise 1.** You configure `setAllowedOriginPatterns(List.of("https://*.example.com"))` and `allowCredentials(true)`. Another service lets users publish JavaScript at `https://files.example.com`. Question: is the pattern safe for an API containing logged-in user data?

**Suggested answer:** It cannot be assumed safe. The `files.example.com` site matches the pattern and becomes an origin allowed by the browser to read credentialed responses (when cookies and related rules permit). Remove the broad wildcard, use an exact origin list, and isolate untrusted content domains.

**Exercise 2.** Preflight has `Origin: https://acme.tenant.example.com`, `Access-Control-Request-Method: DELETE`, while `allowedMethods` only contains `GET`. Should you add `OPTIONS` to let the request pass?

**Suggested answer:** No. The requested method is `DELETE`, which is outside the policy. Adding `OPTIONS` does not authorize `DELETE`; only add `DELETE` if the endpoint genuinely needs it and has corresponding authorization/CSRF controls.

**Exercise 3.** An API responds with `Access-Control-Allow-Origin: https://acme.tenant.example.com`, yet fetch with `credentials: "include"` is still blocked by the browser. What should you check?

**Suggested answer:** Check `Access-Control-Allow-Credentials: true`, preflight policy, requested headers/methods, cookie and browser configuration (`SameSite`, `Secure`, third-party cookies), and the final response through any proxy. CORS allowing response reading does not guarantee the browser sends cookies.

## Key Takeaways

`allowedOriginPatterns` is a useful tool for expressing domain-based allowlists, yet **a broad pattern means a broad set of origins allowed to read responses**. In Spring Security Servlet, integrate CORS via `http.cors(...)` with a clear configuration source, keep the whitelist narrow by scheme/host/port/API path, test both allowed and rejected cases, and never use CORS as a substitute for endpoint security mechanisms.