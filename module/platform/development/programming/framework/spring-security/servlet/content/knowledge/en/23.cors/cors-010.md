# Diagnosing CORS: Rejected Preflight, Missing Headers, and Duplicate Proxy Config — Spring Security Servlet

## 1. Understanding the Diagnostic Problem

When a browser reports a **Cross-Origin Resource Sharing (CORS)** error, the root cause may lie across multiple layers: the **OPTIONS preflight** request received 401/403 from Spring Security or a proxy, the preflight/actual response lacked required headers, the origin did not match, or multiple layers added `Access-Control-Allow-Origin`. Simply glancing at the Console message and adding `Access-Control-Allow-Origin: *` often masks the root cause and can introduce new bugs.

This lesson focuses on **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet** applications, possibly running behind Nginx/Ingress/CDN. The goal is to pinpoint which request failed, which layer produced the response, which header is actually wrong, and how to apply a narrow fix without compromising authentication, authorization, or CSRF.

An **origin** is defined by *scheme + hostname + port*; for example `http://localhost:5173` differs from `http://localhost:8080` even on the same machine. Path is not part of the origin. CORS is a policy used by the **browser** to allow JavaScript from origin A to read responses from origin B; it is **not** an API authentication/authorization mechanism. `curl` does not block responses under CORS, yet is useful for inspecting HTTP status/headers.

## 2. What Is Preflight, and What Conditions Trigger Browser OPTIONS?

Before certain cross-origin requests outside the CORS-safelisted group, the browser sends an **OPTIONS** request to ask whether the server accepts the intended method and headers. Common preflight triggers:

- Methods `PUT`, `PATCH`, `DELETE`.
- Headers added by JavaScript such as `Authorization`, `X-Tenant`, `X-Request-Id`.
- `POST` with `Content-Type: application/json` (not in the safelisted Content-Type group).

An ordinary cross-origin GET without custom headers may **not require preflight**, yet the actual response must still satisfy CORS. Therefore, not seeing OPTIONS **does not mean** CORS is working properly.

For example, frontend `http://localhost:5173` intends to call GET `http://localhost:8080/api/hello` with an Authorization header. The browser may send:

```http
OPTIONS /api/hello HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

This is a **permission-seeking** request. `Access-Control-Request-Headers: authorization` announces that the actual request will carry an `Authorization` header, yet OPTIONS **does not contain the user's Authorization value**. Browsers normally do not attach cookies/credentials to preflight; thus forcing OPTIONS to authenticate like an actual request easily causes 401.

A valid preflight response might look like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Status **200 or 204** can be valid. This is a formatting illustration, not a fixed output of every Spring/proxy version. `Vary` can appear as multiple lines or a single comma-separated line of header names; header order does not determine correctness.

If preflight is rejected, **the actual request is normally not sent by the browser**. If OPTIONS passes yet actual GET/POST returns 401/403/500, that must be investigated separately.

### 2.1. Table for Reading Headers by Role

| Header | In which request/response? | Meaning and common mistakes |
| --- | --- | --- |
| `Origin` | Browser request | Frontend origin; must be in allowed origins |
| `Access-Control-Request-Method` | OPTIONS request | HTTP method the browser wants to send in the actual request |
| `Access-Control-Request-Headers` | OPTIONS request | Request header names needing approval, e.g., `authorization,content-type` |
| `Access-Control-Allow-Origin` | Preflight and actual response | **One** permitted origin or `*` when appropriate; does not accept comma-separated origins |
| `Access-Control-Allow-Methods` | Preflight response | Permitted methods; no need to add OPTIONS just because the check request is OPTIONS |
| `Access-Control-Allow-Headers` | Preflight response | **Request headers** the browser is allowed to send |
| `Access-Control-Allow-Credentials` | CORS response | Must be `true` when permitting the browser to read a credentialed request's response |
| `Access-Control-Expose-Headers` | Actual response | Additional **response headers** JavaScript may read; does not substitute for Allow-Headers |
| `Access-Control-Max-Age` | Preflight response | Hint for browser preflight caching; browser decides the cap |
| `Vary` | Response/cache | Prevents caches from serving one origin/method/header's result for another |

**Distinguish clearly:** `Access-Control-Allow-Headers` governs `Authorization` or `Content-Type` **sent up**; `Access-Control-Expose-Headers` determines whether client script can read response headers like `X-Request-Id`.

## 3. Diagnostic Workflow in DevTools

Open Network, select **All**, and enable Preserve log if navigations occur. Record the frontend origin, final API URL, actual request method, actual headers intended to be sent, OPTIONS status, and actual request status. Rely on Network entries rather than reading only Console because browsers may hide response details on CORS violations.

### Case A — OPTIONS Returns 401

Look for `WWW-Authenticate` or a redirect to login. Very common when Spring Security authentication runs **before** CORS processing, or a proxy/gateway demands credentials on all `/api/**` requests. Preflight normally carries no cookies/Authorization; it must be evaluated by **origin + method + requested headers**, while authentication applies to the actual request.

The preferred fix in Spring Security Servlet is integrating CORS before authentication using `http.cors(Customizer.withDefaults())` and a proper `CorsConfigurationSource`. Do not open `permitAll()` on the entire API just to mask OPTIONS 401s.

### Case B — OPTIONS Returns 403

Distinguish **CORS policy rejection** from **WAF/proxy or security rule rejection**. Spring can return 403 with body similar to `Invalid CORS request` when origin, method, or requested header is disallowed. Check:

1. Does `Origin` match the whitelist on scheme/host/port?
2. Is `Access-Control-Request-Method` in allowed methods?
3. Are all names in `Access-Control-Request-Headers` in allowed headers?
4. After reverse proxy URL rewriting, does the path still match the CORS mapping?
5. Was OPTIONS blocked before reaching Spring?

Do not jump to concluding 403 is CSRF. Spring Security by default does not apply CSRF to safe methods like OPTIONS, though custom filters, gateways, and bespoke rules can cause separate errors.

### Case C — OPTIONS 200/204 Yet Console Still Reports CORS

A 2xx status **is not enough**. Compare request and response headers:

- Missing `Access-Control-Allow-Origin` or value mismatches origin? Check mapping/config/proxy-modified response.
- Using `Access-Control-Allow-Origin: *` with credentialed requests? Browsers reject that combination; a concrete allowed origin is required.
- Missing `Access-Control-Allow-Methods` for the intended method? Add the exact method.
- Missing `Access-Control-Allow-Headers` for `authorization`, `content-type`, or custom headers? Permit the exact request headers genuinely needed.
- Are there **two lines** of `Access-Control-Allow-Origin` or one line containing multiple comma-separated origins? Check layers adding duplicate headers.
- Did OPTIONS redirect 301/302/307/308? Avoid redirecting preflight; use the final canonical URL and let OPTIONS be answered directly.

### Case D — OPTIONS Passes, Actual Request Fails

Inspect the **actual** status and response: 401 may be unauthenticated, 403 may be missing permissions or CSRF token, 404 is routing, 500 is server error. The actual response still needs proper CORS headers so JavaScript can observe the error. If a proxy generates an error response without CORS headers, the browser may report it as a CORS error even though the root cause is an upstream error.

### Case E — No OPTIONS Visible

A safelisted GET or POST can go straight to the server. Check `Origin` and `Access-Control-Allow-Origin` on the actual response. If DevTools is filtering to only one request type, switch to All and inspect the preflight entry. Do not treat the absence of OPTIONS as a bug to "fix" by manually sending OPTIONS from the frontend.

## 4. Reproducing with curl: Comparing Backend and Proxy

Suppose the backend is at `http://localhost:8080`, reverse proxy at `http://localhost:8081`, and frontend origin at `http://localhost:5173`. Send the same simulated preflight to the backend:

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/hello' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Then change only the target to the proxy, keeping headers identical:

```bash
curl -i -X OPTIONS 'http://localhost:8081/api/hello' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

`curl -i` lets you inspect raw status and headers. If the backend returns 200 with **one** allowed origin, yet the proxy returns two lines or a comma-joined value, the problem arises at the proxy or a layer in front of the backend. If the backend itself lacks headers, fix it in the Spring configuration. If the proxy returns 401 while the backend returns 200, look for an authentication rule at the proxy/ingress.

On Windows PowerShell use `curl.exe`; line continuation `\` is Bash-style shell syntax, not PowerShell. You can put the command on one line to avoid shell differences.

Testing the actual request (when the API has the HTTP Basic demo shown below):

```bash
curl -i -u learner:demo-password \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/hello'
```

CORS headers must also be valid on the actual response. `curl` **does not replace** browser testing because it does not apply browser CORS or cookie rules.

## 5. Configuring Spring Security Servlet in the Right Order

The runnable example uses **Java 17+**, Spring Boot 3.x, `spring-boot-starter-web`, and `spring-boot-starter-security`. The demo controller handles only GET to illustrate preflight with `Authorization` while keeping the CSRF story separate for cookie-backed POST endpoints.

Source structure:

```text
src/main/java/com/example/cors/
  CorsDiagnosisApplication.java
  SecurityConfig.java
  HelloController.java
```

**`CorsDiagnosisApplication.java`**

```java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDiagnosisApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.cors;

import java.util.List;

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

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

**`HelloController.java`**

```java
package com.example.cors;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello from API");
    }
}
```

In the example, `.cors(Customizer.withDefaults())` uses the `CorsConfigurationSource` bean for `/api/**` so CORS runs before Spring Security's authentication step. A GET preflight with `authorization` receives a CORS response **without needing** `-u` or a real Authorization header; the actual GET must still pass HTTP Basic.

The hardcoded account is for local testing only. Never embed HTTP Basic passwords in a production frontend. This configuration **keeps Spring Security's default CSRF**. If state-changing POSTs are added, CSRF must still be analyzed per the real credential mechanism; do not disable CSRF globally just upon seeing a 403 error.

### 5.1. Running and Verifying

In the created Gradle Spring Boot project:

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`.

Send the preflight from Section 4: expected 2xx, one `Access-Control-Allow-Origin: http://localhost:5173`, allowed method GET, allowed header authorization, `Access-Control-Allow-Credentials: true`. Do not treat this as a guarantee of header order or response body text across every Spring version.

Send a preflight requesting an **undeclared** header:

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/hello' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-unknown-header'
```

With the sample configuration, it is expected to be rejected (usually 403). If a header is genuinely needed by business logic, add that exact header name to `allowedHeaders`, rather than opening all headers indiscriminately.

Try an origin outside the whitelist:

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/hello' \
  -H 'Origin: http://evil.example.test' \
  -H 'Access-Control-Request-Method: GET'
```

With the policy above, that origin must be rejected.

## 6. Missing Headers: Symptom → Cause Lookup Table

| Symptom | Likely explanation | Diagnosis/fix |
| --- | --- | --- |
| OPTIONS 401 and `WWW-Authenticate` | Auth filter/proxy forces preflight login | CORS before authentication; do not require credentials on OPTIONS |
| OPTIONS 403, body `Invalid CORS request` | Origin/method/header whitelist mismatch | Match the three preflight request headers accurately against policy |
| OPTIONS 302 to `/login` | Login redirect instead of CORS response | Adjust filter/proxy routing to handle preflight directly |
| `No 'Access-Control-Allow-Origin' header` | Route lacks CORS mapping, proxy error response, or Origin not forwarded | Compare backend vs. proxy with same `Origin`; check actual status |
| Origin mismatch | Wrong scheme, host, port, or environment | Whitelist exact origin; do not use URL paths |
| `Request header field authorization is not allowed` | Authorization missing from Allow-Headers | Add this request header if the API genuinely uses it |
| `Request header field content-type is not allowed` | JSON request preflight needs Content-Type | Add Content-Type to allowed headers |
| PUT/DELETE method not allowed | Allowed methods omits the intended method | Add method per API/authorization requirements |
| Missing Allow-Credentials | Frontend sends credentials, response disallows | If design requires credentials, use `allowCredentials(true)` and concrete origin |
| `Access-Control-Allow-Origin: *` with credentials | Wildcard invalid with credentialed response | Return **one** whitelisted origin, not `*` |
| Two Access-Control-Allow-Origin lines | Proxy and app both add headers or overlapping layers | Keep only one CORS owner |
| OPTIONS passes yet actual POST gets 403 | Likely business CSRF/authorization | Inspect actual response and logs; do not loosen CORS blindly |
| Browser does not send cookies | Wrong credentials mode, `SameSite`, `Secure`, Domain/Path, or third-party policy | Fix cookie/fetch policy, not Allow-Headers |
| `Access-Control-Expose-Headers` missing | JS cannot read a custom **response** header | Set exposed headers properly if client needs to read it |
| CORS header on 200 response yet missing on 500 | Proxy/gateway generates error response without CORS | Inspect the exact layer producing the error response and its policy |

**Note:** `Access-Control-Allow-Origin` does not accept multiple comma-separated origins. For credentialed requests, `*` is invalid even if the response contains `Access-Control-Allow-Credentials: true`. Some Spring configurations also reject combining `allowedOrigins("*")` and `allowCredentials(true)` during validation.

## 7. Duplicate Configuration at Reverse Proxy, Ingress, or CDN

Common chain:

```text
Browser -> CDN/WAF -> Ingress/Nginx -> Spring Security -> Spring MVC
```

Suppose Spring returns:

```http
Access-Control-Allow-Origin: http://localhost:5173
```

yet Nginx also has:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    add_header Access-Control-Allow-Origin "http://localhost:5173" always;
    add_header Access-Control-Allow-Credentials "true" always;
}
```

The proxy can cause the response to contain **two** Access-Control-Allow-Origin lines, or merge them into:

```http
Access-Control-Allow-Origin: http://localhost:5173, http://localhost:5173
```

Both forms are invalid for `Access-Control-Allow-Origin`; the browser does not deduplicate two identical values into one.

### 7.1. How to Fix When Spring Owns CORS

If Spring already has a unified policy configured and can handle OPTIONS, let **Spring be the sole layer producing CORS response headers**. The proxy performs routing/forwarding:

```nginx
server {
    listen 8081;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Remove `add_header Access-Control-Allow-*` directives in Nginx and equivalent rules in Ingress/CDN/Gateway. Verify the **effective** configuration and reload properly before testing through the proxy. This is only a snippet illustrating the CORS/forwarding part, not a complete production reverse proxy config.

If the architecture chooses the **proxy** as the CORS owner, it must fully handle origin whitelisting, OPTIONS, allowed methods/headers, credentials, error responses, and caching; meanwhile the backend must not emit another set of headers causing duplicates. Do not split half in the app and half in the proxy for the same endpoint without control.

### 7.2. Tracing the Layer Causing Duplicates

Compare the same request from **direct backend → ingress/proxy → endpoint behind CDN**:

1. Count `Access-Control-Allow-Origin` lines on every response, including cases merged into CSV.
2. Read the status: 200 at backend yet 401 at proxy indicates auth/proxy policy involvement.
3. Check whether `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` are forwarded across every hop.
4. Check path rewrites: CORS configured only for `/api/**` while the proxy rewrites to another route can cause policy mismatch.
5. Inspect rules equivalent to `add_header ... always`, Ingress annotations, and CDN Response Header Rules: they can add headers even on 401/403/500.
6. Check cache keys, TTL, and `Vary` if there are multiple frontend origins or preflight results vary by method/header.

Simply adding another header at the proxy does not cure an already broken response; it can make the bug worse. A consistent policy with exactly one owning layer makes debugging and auditing easier.

## 8. Relationship Between Spring Security CORS, Spring MVC, and Filter Order

A Servlet application can declare CORS via:

- `CorsConfigurationSource` + `http.cors(...)` in `SecurityFilterChain`.
- Spring MVC `WebMvcConfigurer#addCorsMappings`.
- `@CrossOrigin` on a controller or handler method.
- A separately registered `CorsFilter` with a specific filter order.
- Headers created directly at ingress/proxy/CDN.

**It is not guaranteed** that using two Spring mechanisms automatically emits duplicate headers: the framework may combine policies or skip processing a second time. Still, scattered policies cause matchers, allowed methods, credentials, and filter orders to diverge. Pick a centrally managed mechanism and verify the right `SecurityFilterChain` handling API URLs, especially if the app has **multiple** filter chains.

If `CorsConfigurationSource` only registers `/api/**`, a request rewritten to `/other/**` after a proxy rewrite may fail to find a policy. When endpoint A has headers and B does not, inspect the mapping and matcher of the **exact request** before editing the origin whitelist.

## 9. MockMvc Testing for the Right Flow

Add test dependencies `spring-boot-starter-test` and `spring-security-test`. Place file **`src/test/java/com/example/cors/CorsDiagnosisTests.java`**:

```java
package com.example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsDiagnosisTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void permittedPreflightDoesNotNeedAuthentication() throws Exception {
        mockMvc.perform(options("/api/hello")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "http://localhost:5173"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void unlistedRequestHeaderIsRejected() throws Exception {
        mockMvc.perform(options("/api/hello")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "x-unknown-header"))
            .andExpect(status().isForbidden());
    }

    @Test
    void untrustedOriginIsRejected() throws Exception {
        mockMvc.perform(options("/api/hello")
                .header("Origin", "http://evil.example.test")
                .header("Access-Control-Request-Method", "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualGetKeepsCorsHeaders() throws Exception {
        mockMvc.perform(get("/api/hello")
                .with(user("learner"))
                .header("Origin", "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "http://localhost:5173"));
    }
}
```

Run `./gradlew test`; on Windows use `.\gradlew.bat test`.

The tests verify Spring filter logic inside the JVM: valid preflight **needs no authentication**, invalid requested headers/origins are rejected, and the actual response retains the allowed origin. However, **MockMvc does not pass through Nginx/Ingress/CDN**: duplicate-header errors at proxies only surface when testing HTTP through real infrastructure. For larger applications, add tests for a second approved origin, forbidden PUT/DELETE methods, requests with multiple requested headers, actual 401/403 responses, and differing policies across each security chain.

## 10. Do Not Confuse CORS with Auth, CSRF, Cookies, and Caching

**Authentication** checks who is calling the API; **authorization** checks what that principal may do; **CSRF** prevents forged state-changing requests when the browser automatically sends credentials such as session cookies; **CORS** governs whether JavaScript at another origin may read the result under browser policy. Preflight must be handled appropriately without requiring the actual request's credentials, yet the actual request must still be authenticated and authorized.

An OPTIONS pass does not guarantee an actual POST passes: Spring can return 403 because of a missing CSRF token, or because the user lacks permissions. Do not treat an actual POST's 403 by broadening CORS. Likewise, `Access-Control-Allow-Credentials: true` does not force the browser to send cookies. Cookies remain subject to `SameSite`, `Secure`, Domain/Path, `fetch` credentials mode, and third-party cookie policies. An API over HTTPS differs from `http://` in both origin and cookie policy.

For caches/CDNs, an origin echoed from a whitelist needs `Vary: Origin`. For preflight depending on method/request headers, also check `Vary: Access-Control-Request-Method, Access-Control-Request-Headers`. `Access-Control-Max-Age` is browser preflight caching, not a substitute for proxy cache keys and safe proxy configuration.

If you invoke curl manually **without `Origin`**, the response may lack CORS headers because the server does not recognize it as a cross-origin request. Likewise, OPTIONS without `Access-Control-Request-Method` does not accurately simulate a browser preflight. JavaScript `fetch` should not and normally cannot set `Origin` itself — the browser manages this header.

## 11. Checklist for Real Incidents

1. Record the exact frontend origin, API URL, method, request headers, OPTIONS/actual entries, statuses, and redirect chain.
2. For OPTIONS 401/302, check Spring Security/proxy auth and place CORS handling before authentication.
3. For OPTIONS 403, compare origin, requested method, requested headers, and path against the real policy; separate WAF/gateway errors from Spring errors.
4. For 2xx status where the browser still blocks, check `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers`, `Allow-Credentials`, **and header counts**.
5. If the actual request fails, read the actual request's status/body/logs; check authorization, CSRF, exceptions, and CORS headers on error responses.
6. If duplicate headers appear, compare the backend and every proxy/CDN hop; keep only one layer owning the CORS policy.
7. Verify with MockMvc for Spring logic, curl with the exact same request set before/after the proxy, and browser DevTools after clearing/refreshing preflight cache appropriately.

**Core principle:** always identify **which request** failed, **which header** is invalid, and **which layer** produced the response. Fix CORS policy at the right layer; never disable authentication/CSRF or add wildcards or duplicate headers to mask symptoms.
