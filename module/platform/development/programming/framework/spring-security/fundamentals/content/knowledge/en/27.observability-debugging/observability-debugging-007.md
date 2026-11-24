# Distinguishing Browser CORS Errors from Server-Side Authentication Failures

## 1. Why Can an Error Displayed as "CORS" Actually Originate from Authentication?

Suppose the frontend runs at `http://localhost:5173` and the Spring Boot backend at `http://localhost:8080`. The user clicks a button to load profile info and the browser prints:

```text
Access to fetch at 'http://localhost:8080/api/me'
from origin 'http://localhost:5173' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present ...
```

It is tempting for a team to conclude "just add `@CrossOrigin("*")` or disable Spring Security." That conclusion can be wrong and dangerous. The server may have returned **401 Unauthorized** because the user is not logged in or **403 Forbidden** because they lack permission, yet the error response lacked CORS headers so **JavaScript is barred from reading the response body/status**. An authentication failure is thus **masked by a CORS symptom** in the browser.

Conversely, a request may be **blocked by CORS right at preflight** even when the user already holds a valid token. Or the failure may have nothing to do with CORS or authentication: bad TLS certificate, failed DNS resolution, backend down, request blocked by a browser extension, or an HTTPS page calling an HTTP API.

Three questions must be answered **independently**:

1. **Is the browser allowed to read the cross-origin response?** This is a CORS / Same-Origin Policy check.
2. **Did the server accept the request's identity?** This is authentication, typically associated with 401.
3. **Is that identity permitted to perform the action?** This is authorization, typically associated with 403.

A single request can fail at multiple layers simultaneously. Therefore, the goal of this guide is to **observe and debug** accurately with DevTools, HTTP traces/logs, `curl`, Spring Security, and MockMvc tests—not to "fix" it by opening all origins or disabling security.

Scope: **Spring Security Servlet, Spring MVC, Java 17+, and Spring Boot 3.x / Spring Security 6.x**. Reactive WebFlux uses `CorsWebFilter`/`SecurityWebFilterChain` and different APIs; do not copy Servlet examples verbatim to WebFlux.

## 2. What Does CORS Actually Control?

The **Same-Origin Policy (SOP)** restricts JavaScript from one origin from reading data from another origin. An origin is defined by the tuple **scheme + host + port**:

| URL | Compared to `http://localhost:5173` | Why |
| --- | --- | --- |
| `http://localhost:5173/app` | Same origin | Scheme, host, and port all match. |
| `http://localhost:8080/api` | Different origin | Port 8080 differs from 5173. |
| `https://localhost:5173/app` | Different origin | HTTPS scheme differs from HTTP. |
| `http://127.0.0.1:5173/app` | Different origin | Host `127.0.0.1` differs from `localhost`. |
| `https://api.example.com` | Different origin from `https://app.example.com` | Different subdomain; the two origins are not identical. |

**Cross-Origin Resource Sharing (CORS)** is the mechanism by which **the server tells the browser** which origins are allowed to read its responses. For example:

```http
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
```

This **does not authenticate the user**; it only informs the browser which origin may share the response. An unauthenticated caller can still get 401 even when `Access-Control-Allow-Origin` is completely right. An authenticated caller lacking permissions can still get 403. And a script on a disallowed origin cannot read the response under CORS rules even if the endpoint is public.

Foundational points:

- **CORS is primarily enforced by browsers.** `curl`, Postman, or backend-to-backend HTTP clients do not enforce the Same-Origin Policy. They can receive 200, 401, or 403 even while a browser reports a CORS error.
- **CORS does not replace authentication, authorization, CSRF, or firewalls.** An insecure endpoint does not become secure merely by omitting CORS headers. Non-browser clients can still call the API.
- **Having CORS headers does not mean the request is authorized.** It only lets JavaScript inspect the status/body if all CORS rules for the request are satisfied.
- **Absence of `Origin` does not prove a forged request**, because many non-cross-origin-fetch requests omit this header. Never rely on `Origin` alone as a login or authorization mechanism.
- **Origin and site are not the same.** CORS compares scheme/host/port, whereas `SameSite` cookies rely on the concept of a site. Two origins on different ports can belong to the same site; cross-site cookies carry separate `SameSite`/`Secure` constraints.

## 3. Preflight: The OPTIONS Request Can Fail Before the Real Request

When the frontend sends a cross-origin request with a method, header, or content type that requires pre-checking, the browser automatically issues a **CORS preflight request** using `OPTIONS`. For example, when JavaScript wants to send an `Authorization` header:

```http
OPTIONS /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Key point: this request **asks whether sending GET with an Authorization header is allowed**, and **is not** the actual GET. Normally, preflight does not carry the `JSESSIONID` session cookie or bearer token to authenticate the user. It carries metadata needed to check **origin + method + header names**, not token values.

If CORS permits it, the server returns a response like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Exact values, ordering, and presence of `Vary`/`Access-Control-Max-Age` vary by configuration/framework. The browser inspects these headers and can then send the real GET request. **A successful preflight response does not prove the GET will succeed or be authenticated.**

If preflight receives 401 because Spring Security demanded login before CORS ran, or receives 403 because the origin/method/header is disallowed, the browser may **never send the real GET**. That is a CORS/preflight-layer failure; do not tell users to "log in again" when the fault lies in filter ordering or the origin allowlist.

### 3.1. Which Requests May Skip Preflight?

Requests using simple methods (`GET`, `HEAD`, or `POST`) with CORS-safelisted headers and matching `Content-Type` values can be sent **directly** without preflight. For instance, a cross-origin `GET` with only `Accept: application/json` usually does not trigger preflight. In that case, the server receives **the real request** and may return 401 or 403 immediately.

Conversely, `Authorization`, custom `X-...` headers, `PUT`, `DELETE`, or `Content-Type: application/json` trigger preflight in many situations. Browser versions and network policies also affect behavior. **Never intentionally strip authentication or security headers just to avoid preflight.**

### 3.2. Why Must Spring Security Process CORS Before Login Checks?

Preflights normally carry no credentials. If a filter requiring `Authentication` runs ahead of CORS, it can reject `OPTIONS` with 401/403. Spring Security integrates `CorsFilter` via the `http.cors(...)` DSL and `CorsConfigurationSource` so CORS runs in the right order.

Do not mistakenly think that simply adding:

```java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

fixes every CORS error. That line affects only **authorization rules**; it does not emit `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, or `Access-Control-Allow-Headers`, nor allow the browser to read responses. To support OPTIONS properly, configure CORS properly first, and add authorization rules only if genuinely needed.

## 4. Three Failure Patterns That Look Similar Yet Have Different Causes

### Case A — Preflight Fails, Real Request Is Never Sent

```text
Browser frontend (5173)
  -> OPTIONS /api/me [Origin, Request-Method, Request-Headers]
  <- 403 / 401 / missing CORS headers
  -> DOES NOT send GET /api/me
  -> Console reports preflight/CORS; fetch has no readable HTTP response
```

How to handle: inspect the OPTIONS request in the Network tab, `Origin`, requested method/headers, CORS filter order, and server policy. If 401 came from authentication before CORS processed the preflight, fix CORS integration/filter order. If the origin is genuinely unauthorized, **do not loosen permissions carelessly**.

### Case B — GET Request Returns 401/403 With Valid CORS Headers

```http
GET /api/me HTTP/1.1
Origin: http://localhost:5173
```

```http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: http://localhost:5173
WWW-Authenticate: Basic realm="demo-api"
```

The browser lets JavaScript read `Response.status === 401`. The client must then handle **missing authentication**, such as initiating the right login flow. Do not "fix" this with `allowedOrigins("*")` because CORS is **already working**.

For an authenticated request lacking permissions, the server can return `403 Forbidden` with valid CORS headers. JavaScript reads 403; that is **authorization**, not necessarily a CORS bug.

### Case C — Server Returns 401/403 Yet the Browser Displays CORS

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/json
// No Access-Control-Allow-Origin
```

The request may have reached the server and been checked for authentication, yet because valid CORS headers are missing, the browser prevents JavaScript from seeing the response. In JS, `fetch` typically rejects with a `TypeError` instead of yielding a `Response` with status 401.

**Two problems coexist**: invalid credentials (401) *and* response sharing failure (CORS). Fix the configuration so error responses for allowed origins also include CORS headers; **never** turn 401 into 200 and **never** drop authentication rules.

### Case D — Network Errors Misinterpreted as CORS

```text
net::ERR_CONNECTION_REFUSED
TLS/certificate error
DNS resolution error
Mixed content: HTTPS page -> HTTP API
Browser extension/Ad blocker blocked request
```

These errors cannot be solved with `@CrossOrigin`. Check whether the API is running, host/port are right, certificates are valid, mixed content exists, or network middleboxes interfere. MDN also distinguishes "CORS request did not succeed" when connection/network/protocol fails rather than a specific origin policy.

## 5. Quick Identification Matrix in DevTools

| Symptom | Initial Inference | Next Check |
| --- | --- | --- |
| OPTIONS present, returns 401; GET never appears | Preflight blocked by auth layer before CORS, or bad OPTIONS rule | Check `http.cors()`, filter order, security matcher, and logs for OPTIONS. |
| OPTIONS returns 403 "Invalid CORS request" | Origin/method/header disallowed | Compare `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` against config. |
| OPTIONS 200 yet missing proper ACAO/allow-method/allow-header | Preflight not accepted by browser | Check all CORS headers and whether a proxy stripped/altered headers. |
| OPTIONS succeeds, GET returns 401 **with ACAO** | CORS is fine; authentication failed | Check cookies/tokens/Authorization, expiry, and entry point. |
| OPTIONS succeeds, GET returns 403 **with ACAO** | CORS is fine; insufficient permission or another filter returned 403 | Distinguish AccessDenied, CSRF, and app rules in logs. |
| GET returns 401/403 **without ACAO** | Auth/authz failed AND browser cannot read the error | Add CORS handling for error paths too while preserving security statuses. |
| No HTTP status, "connection refused", or TLS error | Infrastructure/connectivity failure | Check server startup, DNS, network, TLS, and mixed content. |
| `curl` returns 200 JSON yet browser reports CORS | `curl` does not enforce SOP; does not prove CORS works | Use DevTools and a request carrying the frontend's real `Origin`. |
| Fails only with `credentials: "include"` | Cookie/credentialed CORS/third-party cookie policy issue | Specific ACAO, ACAC=true, cookie SameSite/Secure, CSRF. |
| 302 redirect to login/IdP then reports CORS | Interactive login unsuitable for fetch/XHR or cross-origin redirect | Inspect redirect chain and design OIDC/login flow properly. |

This table provides **investigative leads**, not automated diagnosis. For instance, a 403 can come from CSRF, the CORS filter, authorization, or a gateway/WAF; check which URL returned 403, Network status, response headers, and logs before concluding.

## 6. Ordered Debugging Workflow: Browser → HTTP → Spring Security → Gateway

### 6.1. In the Browser

1. Open **Developer Tools → Network**, enable **Preserve log** to catch redirects, and filter **Fetch/XHR** (or All to see OPTIONS).
2. Reproduce the error from the real frontend and check **Request URL**, **Request Method**, **Origin**, status, redirect chain, and Console errors.
3. If `OPTIONS` appears, check the three request headers: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`; then inspect `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and response status.
4. If OPTIONS succeeded, find the **real request** (`GET`/`POST`). Check status 401, 403, 404, 500, and whether response headers include ACAO and (when needed) ACAC.
5. Verify whether the real request **carried the expected Authorization/cookie**. Sometimes cookies are omitted due to default `credentials` or `SameSite`/`Secure`/third-party cookie policies, not wrong passwords.
6. Check the **Console** tab for the CORS reason reported by the browser. JavaScript usually **cannot access details** of CORS errors for security reasons, so rely on DevTools Network and server logs.
7. If status is `(blocked)` or the request never connected, check CSP, mixed content, DNS, TLS, extensions, and proxies. Never assume every `TypeError: Failed to fetch` is CORS.

**Never share DevTools screenshots containing Authorization headers, Cookies, access/refresh tokens, session IDs, or personal info.** When writing tickets or logs, include only statuses, sanitized routes, and safe correlation IDs.

### 6.2. Using `curl` Appropriately

A `curl` call **without Origin** tests the endpoint and authentication, yet **does not fully test browser CORS**:

```bash
curl -i http://localhost:8080/api/me
```

If the API uses HTTP Basic and is unauthenticated, a 401 response is expected. Add the frontend's `Origin` to see whether the server returns ACAO:

```bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/me
```

Simulate preflight (a helpful command, not a substitute for a real browser):

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Retry with a disallowed origin:

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://untrusted.example' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Results to distinguish:

- A response with status `401` and `Access-Control-Allow-Origin: http://localhost:5173` indicates **CORS handled the real request**, yet the request is unauthenticated.
- An accepted `OPTIONS` preflight with ACAO, allowed methods, and allowed headers indicates the browser may attempt the real request; it **does not** prove valid identity.
- A disallowed preflight may return 403 without ACAO. That is a **CORS rejection**, not necessarily a missing account role.
- `curl` still prints responses even without ACAO; only **browsers** block JavaScript from reading data under CORS.

### 6.3. In Spring Security

Inspect the `SecurityFilterChain` configuration:

- Is `http.cors(...)` configured? Does it use the right `CorsConfigurationSource` or Spring MVC CORS support?
- Does `securityMatcher` send `OPTIONS` requests or the real URL into a different chain missing the CORS filter?
- Is a custom filter or in-app WAF returning 401/403 **before** CORS runs?
- Is an `anyRequest().authenticated()` rule blocking OPTIONS because it has no cookie?
- Which `AuthenticationEntryPoint` produced 401? Did 403 come from `AccessDeniedHandler`, CSRF, or CORS?
- Do error responses from controllers/`@RestControllerAdvice` or proxies go through the same CORS handling?
- When DEBUG is safely enabled in a test environment, which filter order and request matchers applied?

**Do not merely add `@CrossOrigin` on a controller** and assume every response from security filters is covered, because a request can be rejected before reaching MVC. Integrating CORS into the Spring Security chain proactively governs preflight.

### 6.4. In Proxies / Load Balancers / API Gateways

Sometimes the app returns proper CORS headers while a gateway strips, duplicates, or alters them. Other times the gateway itself returns 401/403/502 **without forwarding the request to the JVM**. Cross-check:

- Request IDs, timestamps, hosts, and paths in proxy and backend logs.
- Whether the response came from ingress/gateway or Spring Security/Servlet.
- Whether `Access-Control-Allow-Origin` was emitted twice; CORS forbids invalid duplicate ACAO values.
- `Vary: Origin` and caching when returning dynamic origins; avoid caching a response with origin A's ACAO and serving it to origin B.
- Whether preflight policies at the gateway and inside the app conflict.

## 7. Java 17+ / Spring Boot 3.x Example: Configuring Proper CORS While Preserving 401/403

Demo design:

- Allowed frontend: `http://localhost:5173`.
- Backend: `http://localhost:8080`, using HTTP Basic **for illustration only**.
- `GET /api/public/ping` is public; `GET /api/me` requires login; `GET /api/admin/report` requires role ADMIN.
- Demo user `reader` has role READER, **not** ADMIN.
- CORS allowed only for the listed origin, GET/OPTIONS methods, and Authorization/Content-Type headers.
- Preflight is processed by CORS before authentication; API 401/403 responses still carry ACAO for the allowed origin. Other origins are rejected.
- No disabling CSRF, no opening all origins, no removing authorization.

**Limitation:** HTTP Basic sends credentials on every request, so real systems must use **HTTPS** and proper password management. Demo accounts and passwords here are test data only; never embed real passwords in source code or frontends.

### 7.1. Dependencies

Create a Spring Boot 3.x project with the Gradle plugin, Java 17+ toolchain, and add the dependencies in `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependencies snippet**, not a complete build file. All Java classes share the `demo.corsdiagnosis` package.

### 7.2. Startup Application

File `src/main/java/demo/corsdiagnosis/CorsDiagnosisApplication.java`:

```java
package demo.corsdiagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDiagnosisApplication.class, args);
    }
}
```

### 7.3. `CorsConfigurationSource` and `SecurityFilterChain`

File `src/main/java/demo/corsdiagnosis/SecurityConfig.java`:

```java
package demo.corsdiagnosis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
public class SecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Only the approved frontend; never use "*" with credentials.
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false); // Demo does not use cross-origin cookies.
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CorsConfigurationSource corsSource
    ) throws Exception {

        http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Do not disable CSRF. Example has only GET endpoints.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("READER")
                .build()
        );
    }
}
```

**Exact responsibility breakdown:**

- `corsConfigurationSource()` permits only `http://localhost:5173`. `localhost` differs from `127.0.0.1`; `http` differs from `https`; port is also part of the origin.
- `registerCorsConfiguration("/api/**", cors)` attaches the policy to the API. Another route without matching CORS configuration is not automatically shared cross-origin.
- `.cors(cors -> cors.configurationSource(corsSource))` integrates CORS handling into Spring Security and routes preflights properly. Once a real request is allowed by CORS, authentication and authorization still execute.
- `.setAllowedHeaders(List.of("Authorization", "Content-Type"))` lets the browser request those headers during preflight; it **does not validate** that the `Authorization` header value is valid.
- `setAllowCredentials(false)` fits an example without CORS cookies; cross-origin cookies require a distinct constrained setup.
- `requestMatchers("/api/admin/**").hasRole("ADMIN")` gives the demo READER user a 403. `/api/me` requires authentication, so requests without credentials return 401 via Basic.
- `anyRequest().denyAll()` prevents endpoints outside the demo scope from being accidentally exposed.
- `httpBasic(...)` uses built-in Spring Security rather than a hand-rolled filter parsing Basic headers. When switching to Bearer/JWT, swap the auth mechanism while keeping CORS policy and permissions **separate**.
- No `csrf.disable()`: state-changing requests using sessions/cookies must still evaluate CSRF independently, unrelated to configuring CORS for GET.

**Important note on beans:** the code explicitly passes `CorsConfigurationSource` to the DSL so it does not rely on which CORS bean Spring Security auto-picks when multiple sources exist. In large apps with multiple `SecurityFilterChain` beans, decide the policy and matcher position for **each chain**.

### 7.4. Controller

File `src/main/java/demo/corsdiagnosis/DemoController.java`:

```java
package demo.corsdiagnosis;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("result", "pong");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/admin/report")
    public Map<String, Boolean> adminReport() {
        return Map.of("ok", true);
    }
}
```

These GET endpoints are for diagnostic illustration only. Never implement state-mutating operations over GET in real apps. For unauthenticated callers, the `/api/me` controller **never executes**; Security blocks it first. For user READER, `/api/admin/report` is denied before the controller. CORS can still attach headers to error responses.

### 7.5. JavaScript Observing Errors in the Browser

Serve a frontend at `http://localhost:5173` and run in DevTools Console:

```javascript
async function checkApi() {
  try {
    const response = await fetch("http://localhost:8080/api/me", {
      mode: "cors"
    });

    console.log("HTTP status:", response.status);
    console.log("Readable by JS:", true);

    if (response.status === 401) {
      console.log("Request needs authentication");
    } else if (response.status === 403) {
      console.log("Authenticated account lacks access, or request was denied");
    }
  } catch (error) {
    console.log("No readable HTTP response");
    // Not yet definitive proof of a CORS failure:
    // could be TLS, DNS, connection failure, mixed content...
    console.error(error);
  }
}
checkApi();
```

Against the sample server and allowed origin, a request without Authorization typically produces a **401 readable by JavaScript**, not a CORS exception. A `fetch` resolving with status 401 is a normal HTTP result; `fetch` **does not reject** simply because a response has status 401 or 403.

Running the same code from a disallowed origin can trigger a CORS error and hit `catch`, even though the server generated a different response. Never assume `catch` always means bad password.

Never keep demo passwords in production JavaScript to test authentication; authenticated and authorization cases below are verified via MockMvc or test HTTP clients.

## 8. MockMvc Testing: Preflight and Authentication Are Separate Assertion Groups

File `src/test/java/demo/corsdiagnosis/CorsAndAuthenticationTests.java`:

```java
package demo.corsdiagnosis;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAndAuthenticationTests {

    private static final String ALLOWED_ORIGIN = "http://localhost:5173";
    private static final String REJECTED_ORIGIN = "https://untrusted.example";

    @Autowired
    MockMvc mvc;

    @Test
    void preflightFromAllowedOriginIsAcceptedWithoutLogin()
            throws Exception {
        mvc.perform(options("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"
                ))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ))
            .andExpect(header().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS
            ))
            .andExpect(header().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS
            ));

        // No Authorization/cookie, yet OPTIONS is still handled by CORS.
    }

    @Test
    void preflightFromRejectedOriginDoesNotGrantCors() throws Exception {
        mvc.perform(options("/api/me")
                .header(HttpHeaders.ORIGIN, REJECTED_ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"
                ))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
            ));
    }

    @Test
    void actualGetWithoutCredentialsIs401ButCorsSucceeds()
            throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ));
    }

    @Test
    void invalidPasswordIsStill401WithCorsHeaders() throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ));
    }

    @Test
    void authenticatedReaderCanReadMeWithCors() throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .with(httpBasic("reader", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ))
            .andExpect(jsonPath("$.user").value("reader"));
    }

    @Test
    void readerCannotAccessAdminBut403IsReadableByBrowser()
            throws Exception {
        mvc.perform(get("/api/admin/report")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                .with(httpBasic("reader", "demo-password")))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ));
    }

    @Test
    void requestWithoutOriginStillUsesServerAuthentication()
            throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
            ));
    }

    @Test
    void publicEndpointFromAllowedOriginWorks() throws Exception {
        mvc.perform(get("/api/public/ping")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN
            ))
            .andExpect(jsonPath("$.result").value("pong"));
    }
}
```

Run in a Spring Boot project with Gradle wrapper:

```bash
./gradlew test --tests demo.corsdiagnosis.CorsAndAuthenticationTests
```

These are **8 tests designed to check expected behavior**; this guide does not claim to have executed the command in the reader's environment. With the right configuration, all 8 cases should PASS. They verify:

| Case | Expected HTTP Status | CORS Headers | What It Proves |
| --- | --- | --- | --- |
| Preflight allowed origin, no login | 200 | Exact ACAO, allow-method/header | No authentication required to query cross-origin permission. |
| Preflight forbidden origin | 403 | No ACAO | CORS rejects origin without exposing the API. |
| Real GET without credentials, valid origin | 401 | Valid ACAO | Authentication failure remains readable in browser. |
| GET with wrong password, valid origin | 401 | Valid ACAO | CORS does not "fix" authentication. |
| GET with valid account | 200 | Valid ACAO | Response sharing and authentication both work. |
| GET admin with READER user | 403 | Valid ACAO | Missing permission differs from CORS failure. |
| GET without Origin | 401 | No ACAO needed | Server still enforces authentication without CORS. |
| GET public, valid origin | 200 | Valid ACAO | Public endpoint matches policy. |

**Testing limitation:** MockMvc simulates requests and the in-app filter chain; it **does not enforce browser CORS policies** and does not test nginx/ingress/CDN. Production still requires end-to-end tests using real browsers, real proxy infrastructure, real cookies, and the actual frontend origin. Still, MockMvc is an effective way to verify **server statuses** and **CORS headers** separately before debugging UI code.

## 9. Differences When Using Session Cookies and `credentials: "include"`

The example above does not send cross-origin cookies. Apps using session cookies must understand **three separate layers**:

1. Does the browser send the cookie, given `fetch(credentials)`, `SameSite`, `Secure`, domain/path, and third-party cookie restrictions?
2. Does CORS allow JavaScript to read the **credentialed response**, given ACAO and ACAC?
3. Does Spring Security recognize that session, permit the operation, and validate CSRF?

A session-cookie frontend might call:

```javascript
const result = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
console.log(result.status);
```

When permitting cross-origin credentials, responses need matching policies, for example:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

In Java configuration, allow **only trusted origins**:

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
cors.setAllowCredentials(true);
```

This is a **replacement configuration snippet** for cookie-based APIs; place it inside an appropriate `CorsConfigurationSource` rather than stacking it onto the HTTP Basic example without updating the auth model.

Common points of confusion:

- When a request carries credentials, **never** return `Access-Control-Allow-Origin: *`; browsers reject wildcards for credentialed CORS.
- `Access-Control-Allow-Credentials: true` **does not cause cookies to be sent** if `SameSite`, `Secure`, domain/path, third-party cookie policies, or `fetch` disallow it.
- Sending a cookie to the API **does not prove the user is authorized**; the session may be expired or lack permissions.
- `SameSite=None; Secure` may be needed for cookies used in **cross-site** contexts, though **cross-origin** and **cross-site** are not identical.
- CORS does not replace **CSRF protection**. Allowing a page to read responses does not mean state-changing requests are exempt from CSRF.
- When using dynamic `Origin` values or origin patterns, ensure the policy is intentional and caches differentiate variants with `Vary: Origin`.

This also helps separate two situations that look nearly identical in browsers: **cookie omitted so the server validly returns 401**, vs **invalid credentialed CORS headers preventing JavaScript from reading even the 401**.

## 10. 401, 403, Redirects, and Login: Confusion in Real Applications

### 10.1. JSON APIs vs. Form-Login Websites

A web app using default `formLogin` may respond to unauthenticated requests with:

```http
HTTP/1.1 302 Found
Location: /login
```

Browser `fetch` follows redirects automatically by default. If a redirect points to another origin, such as an Identity Provider, the outcome can look like a CORS error on the redirect or login page—not because the API account "lost permissions."

For JSON APIs, usually define a status-based 401 contract and have the frontend initiate login properly. For OIDC/OAuth, navigate the user via a **top-level browser redirect** by design rather than calling `fetch` against an IdP's HTML login page as if it were a JSON API. Never open CORS on all IdP origins just to silence the warning.

### 10.2. 403 Does Not Only Mean "Missing Role"

Spring Security or pre-controller components can return 403 when:

- The user is authenticated yet lacks the required authority/role.
- The CSRF token is missing/invalid on a state-changing request with CSRF enabled.
- The CORS filter rejects origin/method/header, typically returning "Invalid CORS request."
- A gateway/WAF blocks the request per its own rules.
- The application intentionally returns 403 per business policy.

Therefore, identify **which filter/handler returned 403**, whether it was `OPTIONS` or the real request, plus logs and response headers. Never automatically conclude "missing role" whenever you see 403.

### 10.3. HTTP 401 Needs an Appropriate Challenge

With HTTP Basic or Bearer, `WWW-Authenticate` is an important part of the protocol. If customizing `AuthenticationEntryPoint` to return JSON, preserve a challenge compatible with the scheme in use. Never disable Spring Security or strip `WWW-Authenticate` just to make 401 resemble another response.

If the browser blocks CORS, JavaScript **cannot read** the 401 body/headers; the fix is a proper CORS policy for origins permitted to view responses, **not** exposing tokens/challenges to arbitrary origins.

## 11. Ways NOT to "Fix CORS"

### 11.1. Using `mode: "no-cors"`

```javascript
// Not a solution for reading a JSON API.
fetch("http://localhost:8080/api/me", { mode: "no-cors" });
```

`no-cors` makes the response **opaque** in many cases: JavaScript cannot read status/body/headers as a normal JSON API; `response.status` is typically 0. It does not "bypass browser security" in a way that lets you consume the response.

### 11.2. Opening CORS to Every Origin

```java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
```

This is invalid for credentialed CORS in modern Spring Framework and is a dangerous design smell. Do not react to a CORS error by allowing all origins. Instead, identify exact frontend origins, methods, headers, and credential needs. When using allowed-origin patterns, audit matched origins carefully and avoid overly broad patterns on sensitive APIs.

### 11.3. Disabling `http.cors()` or All of Spring Security

`http.cors(cors -> cors.disable())` turns off Spring Security's CORS integration; **it does not disable the browser's Same-Origin Policy**. Turning off authorization/CSRF so the browser stops seeing 401/403 can open critical vulnerabilities without even emitting the required CORS headers.

### 11.4. Adding Only `@CrossOrigin`

`@CrossOrigin` in Spring MVC helps at the endpoint/controller level and can be picked up by Spring Security **when CORS is properly integrated**. Yet responses emitted before the controller by security filters, gateways, or other chains must be tested; a controller annotation does not guarantee coverage of every preflight/401/403.

### 11.5. Returning HTTP 200 Just to Suppress Browser Errors

Returning HTTP 200 for unauthenticated requests breaks API contracts and monitoring. If CORS is permitted yet the user is unauthenticated, **401 with ACAO** is the right outcome. For an authenticated user lacking permissions, **403 with ACAO** is likewise right.

### 11.6. Assuming `curl` Succeeding Means the Browser Can Read It

`curl` checks only the HTTP response. Browsers also enforce SOP, CORS credentials, preflight, redirects, and cookie policies. Test both sides.

### 11.7. Adding CORS Headers at Multiple Layers Uncoordinatedly

If both Spring Boot and a gateway inject ACAO, the response may contain **two values** or mix wildcards with specific origins, causing the browser to reject it. Assign one authoritative layer for CORS and inspect the final response arriving at the browser.

## 12. Checking Error Paths, Multiple Chains, and Edge Cases

### 12.1. Errors from a Custom Filter Before CORS

An application filter registered directly with the Servlet container can write an error **before** `springSecurityFilterChain`. When that happens, `http.cors()` inside Spring Security cannot "go back in time" to add headers to an already committed response. Either shift responsibilities, adjust ordering, or ensure responses from that filter follow the CORS policy.

Likewise, responses generated by reverse proxies or API gateways must be configured at the layer producing the error.

### 12.2. Multiple `SecurityFilterChain` Beans

Suppose there is an `/api/admin/**` chain at `@Order(1)` and an `/api/**` chain at `@Order(2)`. `FilterChainProxy` picks **the first matching chain**. If CORS is enabled only on the second chain, admin requests may bypass `CorsFilter`, causing browser CORS errors on admin 401/403 responses. Verify matchers, ordering, and CORS config on **every chain**.

### 12.3. Preflight Cache, Error Caching, and `Vary`

Preflights can be cached by browsers per `Access-Control-Max-Age` within browser caps. After changing CORS config, test with a fresh profile or cache-bypassed devtools so stale results do not mislead you. Still, do not confuse preflight caching with HTTP caching of data responses.

When emitting dynamic ACAO from an allowlist, `Vary: Origin` helps intermediate caches separate variants. For preflight responses, `Vary: Access-Control-Request-Method` and `Vary: Access-Control-Request-Headers` can also matter.

### 12.4. Redirects, OPTIONS, and Failures Outside the App

Do not assume every `302`/`307` on preflight behaves uniformly across browsers. Avoid unnecessary redirects before CORS runs, such as HTTP → HTTPS at the wrong layer or redirecting OPTIONS to login. Configure the frontend to call the exact HTTPS origin directly and inspect redirect chains in DevTools.

If the browser reports **mixed content**, untrusted certificates, DNS, firewall, or connection refused, fix connectivity first: CORS headers exist only when a proper HTTP response arrives.

### 12.5. WebSockets, SSE, and Private Networks

- WebSockets have their own handshake and origin security rules; **do not** treat Fetch CORS tests as proof of WebSocket protection.
- Server-Sent Events/EventSource follow specific cross-origin/credential rules; test with the actual client API used.
- Some browser versions enforce Private Network Access checks. That is an additional browser/environment restriction, not a Spring Security 401/403.

## 13. Priority-Ordered Diagnostic Checklist

When receiving a "frontend CORS error" ticket:

1. **Record the exact source:** frontend origin (scheme/host/port), API URL, method, Network status, and whether OPTIONS ran. Never record real tokens/cookies.
2. **Check network/connectivity:** is the backend up, are DNS/TLS/mixed content healthy, and are browser extensions interfering?
3. **Check preflight:** if OPTIONS exists, inspect status and ACAO/allowed methods/headers; confirm it runs before authentication.
4. **Check the real request:** was it sent; status 200/401/403/500; are CORS headers present on error paths too?
5. **Separate authn/authz:** 401 from missing/bad credentials vs 403 from missing permissions or CSRF/CORS/gateway; inspect security chain/entry point/handler.
6. **Check credentialed CORS:** `fetch.credentials`, cookie attributes, specific ACAO, and ACAC; no wildcards, no casual CSRF disabling.
7. **Cross-check with `curl`:** call with and without Origin, and simulate OPTIONS; remember `curl` does not enforce SOP.
8. **Check Spring:** `CorsConfigurationSource`, `http.cors`, custom filters, multiple `SecurityFilterChain` beans, and error handlers.
9. **Check gateway:** are headers overwritten or duplicated; did 401/403 happen before the backend; did caches mix origins?
10. **Write regression tests:** allowed preflight 200, blocked preflight without ACAO, real request 401/403 with ACAO for allowed origin, 200 success, and browser test from the real origin.

### Final Acceptance Matrix

| Scenario | Right Diagnosis | Passing Criteria |
| --- | --- | --- |
| Valid origin + OPTIONS without credentials | CORS preflight | CORS handles it without requiring login; methods/headers permitted accurately. |
| Invalid origin + OPTIONS | CORS rejection | Blocked origin cannot read response; no wildcard loosening. |
| Valid origin + unauthenticated GET | Authentication | 401, browser can read error response via ACAO. |
| Valid origin + authenticated GET lacking role | Authorization | 403, browser reads status per policy. |
| Valid origin + GET with valid credentials | Happy path | 200, valid JSON, matching ACAO. |
| Cross-origin cookie | CORS + cookie policy + session/CSRF | ACAO does not use `*`, ACAC/cookies right, permissions still checked. |
| Network/TLS failure | Infrastructure | Connectivity fixed; not "fixed" by opening CORS. |
| CORS right in backend yet wrong in browser | Gateway/cache/redirect | Final response in DevTools matches policy with no duplicate headers. |

**Concluding principle:** Never ask "CORS or Security?" as if only one applies. Ask **which request**, **did it reach the server**, **which status was produced where**, **may the browser read that response**, and **is the caller authenticated/authorized**. Adjust configuration only after separating those answers.

## 14. References

- Spring Security 6.5 — [CORS in Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html).
- Spring Security 6.5 — [SecurityFilterChain and Servlet architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html).
- Spring Security 6.5 — [Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html).
- Spring Framework — [CORS and MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html).
- MDN — [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- MDN — [CORS Error Messages and How to Diagnose Them](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors).
- MDN — [Reason: CORS request did not succeed](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSDidNotSucceed).
- MDN — [Fetch API, request credentials, and handling HTTP errors](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch).