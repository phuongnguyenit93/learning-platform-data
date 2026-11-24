# Integrating CORS with `CorsConfigurationSource` in Spring Security Servlet

> **Scope:** Spring Security 6.x on Servlet/Spring MVC (typically with Spring Boot 3.x), Java 17+. This lesson explains providing CORS policy via `CorsConfigurationSource`, wiring it into `SecurityFilterChain`, testing preflight, and distinguishing CORS errors from authentication, cookies, and CSRF. Spring WebFlux has its own reactive mechanism.

## 1. The Problem: Frontend and API on Two Origins

Suppose the frontend at `http://localhost:5173` calls the backend at `http://localhost:8080`. Those are two **different origins** even on the same machine: an origin consists of **scheme + hostname + port**. `https://app.example.com` and `https://api.example.com` are also different origins; the path is not part of the origin.

~~~javascript
const response = await fetch("http://localhost:8080/api/hello", {
  credentials: "include"
});
console.log(response.status);
~~~

Browsers enforce **Cross-Origin Resource Sharing (CORS)** when JavaScript from one origin wants to read a response from another origin. The server needs to declare which origins, HTTP methods, and request headers are allowed. If cookies/sessions are used, the server must also allow credentialed CORS responses.

In an application with Spring Security, a typical challenge is that the browser's **OPTIONS preflight** request normally does not carry a login cookie. If authentication/authorization runs before CORS processing, preflight may be rejected even though the user is already logged in on the frontend tab.

`CorsConfigurationSource` provides the CORS policy for a request and is a standard integration point with Spring Security Servlet. After this lesson, you should be able to answer: "where does this request get its policy from?", "which filter handles OPTIONS?", "why does OPTIONS pass while POST still returns 403?", and "how do we test policy by origin, method, and headers?".

## 2. First Understand CORS Requests and Preflight

### 2.1. Ordinary Cross-Origin Request

A GET request can be sent with `Origin`:

~~~http
GET /api/hello HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

If the policy accepts this origin, the response may contain:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json
~~~

Actual header names/order may vary. With `credentials: "include"`, the response needs appropriate CORS handling for credentials. If the server does not send a valid `Access-Control-Allow-Origin`, the browser may receive the response on the network yet **block JavaScript from reading the response**. Thus a CORS error message in the browser does not by itself prove that the HTTP request never reached the server.

### 2.2. OPTIONS Preflight

A `POST` request using `Content-Type: application/json` or a custom header such as `X-CSRF-TOKEN` typically causes the browser to send a preflight first:

~~~http
OPTIONS /api/items HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

The browser is asking: "Is this origin allowed to call `POST /api/items` with those request headers?" Preflight **is not yet** the business `POST` request, and normally does not send session cookies. A valid response might look like this:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
~~~

Only if accepted does the browser send the actual request; the actual request's response must also have appropriate CORS headers for JavaScript to read it. The browser may cache the preflight result, though the cache duration is still subject to browser limits.

Not every POST triggers a preflight; it depends on the method, content type, and headers per the browser's CORS rules. Conversely, even without preflight, the server still needs appropriate CORS headers in the response of a cross-origin request.

### 2.3. What Does CORS Do and Not Do?

CORS is a browser policy applied to **reading cross-origin responses** and to certain complex cross-origin requests. It **is not** an authentication or authorization layer. `curl`, Postman, or server-to-server services do not enforce the Same-Origin Policy like a browser. Even when an origin is allowed, the backend still needs to verify the user, access permissions, CSRF if authentication cookies are used, validation, and business logic.

## 3. Components and Responsibilities in the Servlet Stack

| Component | Responsibility | Common misconception |
| --- | --- | --- |
| `CorsConfiguration` | Policy data: origins, methods, headers, credentials, exposed headers, max age. | Does not intercept requests or add response headers by itself. |
| `CorsConfigurationSource` | Selects the appropriate `CorsConfiguration` for the current HTTP request. | Can return `null` if the request has no policy. |
| `UrlBasedCorsConfigurationSource` | Implementation mapping URL patterns such as `/api/**` to policies. | Usable out of the box; no custom source needed for typical paths. |
| `CorsFilter`/`CorsProcessor` | Processes `Origin` and preflight headers, checks policy, emits CORS response headers. | Must be positioned properly before filters requiring authentication on preflight. |
| `HttpSecurity.cors(…)` | Connects CORS processing into the Spring Security Servlet filter chain. | Must be on the chain matching the path; not merely a controller setting. |

The interface essentially has the method:

~~~java
CorsConfiguration getCorsConfiguration(HttpServletRequest request);
~~~

This is an API signature to understand the contract, not a standalone runnable Java file. `UrlBasedCorsConfigurationSource` implements this contract by looking up registered paths. When different policies are needed between public and admin APIs, multiple paths can be registered with separate policies.

~~~text
Browser
  |
  +-- OPTIONS /api/items, Origin + Access-Control-Request-*
  |      |
  |      v
  |   Spring Security: CORS processing
  |      |
  |      +--> CorsConfigurationSource -> policy for /api/**
  |      +--> CorsProcessor checks Origin/Method/Headers
  |      +--> allowed: returns preflight response
  |      +--> rejected: no CORS approval granted
  |
  +-- Actual POST /api/items
         |
         v
       CORS processing -> authentication -> CSRF -> authorization
         |
         v
       controller when all required conditions are valid
         |
         v
       response with CORS headers if origin is permitted
~~~

The conceptual order above is for explanation; the exact position among security filters is constructed by Spring Security. What must be ensured is that CORS handles preflight **before authentication blocks it**.

## 4. Practical Example: Registering `CorsConfigurationSource` by Path

The demo application uses Spring Boot 3.x, Java 17+, `spring-boot-starter-web`, and `spring-boot-starter-security`. Dev frontend is at `http://localhost:5173`, production frontend at `https://app.example.com`. The API lives under `/api/**`, authentication is via session/form login, and CSRF is kept at default.

The code below consists of complete Java files **when placed in a Spring Boot project with the stated dependencies**; run via the project's Gradle/Maven, not standalone with `javac` without the Spring classpath. All classes are in package `com.example.corsdemo`.

**`src/main/java/com/example/corsdemo/CorsDemoApplication.java`:**

~~~java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/corsdemo/SecurityConfig.java`:**

~~~java
package com.example.corsdemo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration policy = new CorsConfiguration();

        // Origin is scheme + host + port, excluding path.
        policy.setAllowedOrigins(List.of(
            "http://localhost:5173",
            "https://app.example.com"
        ));

        // Actual request methods permitted in CORS.
        policy.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE"
        ));

        // Request headers the frontend needs to send.
        policy.setAllowedHeaders(List.of(
            "Content-Type",
            "Authorization",
            "X-CSRF-TOKEN",
            "X-XSRF-TOKEN"
        ));

        // Allow the frontend to also read the Location response header.
        policy.setExposedHeaders(List.of("Location"));

        // Intended for flows using cross-origin session cookies.
        policy.setAllowCredentials(true);

        // Duration the browser may cache preflight, in seconds.
        policy.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        // Apply this policy only to /api/**.
        source.registerCorsConfiguration("/api/**", policy);

        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) throws Exception {

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

The most important line is:

~~~java
.cors(cors -> cors.configurationSource(corsSource))
~~~

It connects the **specific** policy source to the Spring Security chain being built. For a request to `/api/items`, the source looks up the policy for `/api/**`. The CORS processor decides whether to accept the `Origin`, method, headers, and credentials before the actual request reaches the remaining layers.

**`src/main/java/com/example/corsdemo/ApiController.java`:**

~~~java
package com.example.corsdemo;

import java.net.URI;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello");
    }

    @PostMapping("/items")
    public ResponseEntity<Map<String, String>> create(
            @RequestBody Map<String, String> input) {
        String name = input.getOrDefault("name", "item");
        return ResponseEntity
            .created(URI.create("/api/items/1"))
            .body(Map.of("id", "1", "name", name));
    }
}
~~~

If an authenticated GET is accepted, the sample JSON is:

~~~json
{"message":"Hello"}
~~~

If an authenticated POST with a valid CSRF token sends JSON `{"name":"Book"}`, the controller returns 201, `Location: /api/items/1`, and JSON:

~~~json
{"id":"1","name":"Book"}
~~~

The controller is illustrative only: id `1` is hardcoded, nothing is saved to a database, and input is not business-validated. CORS does not by itself guarantee data persistence.

### Detailed Explanation of Each Policy Setting

**`setAllowedOrigins(List.of(…))`:** explicit origin allowlist. An origin is `http://localhost:5173`, not `http://localhost:5173/home`. Scheme, host, and port must match; do not use "similar-looking" domains. The `null` origin from special contexts should also not be allowed arbitrarily.

**`setAllowedMethods(…)`:** methods of the actual request that the browser is allowed to call. Preflight automatically sends `OPTIONS` to ask about `POST`/`PUT`/…; **it is not mandatory** to add `OPTIONS` to the method list just because the browser uses preflight. If the application genuinely calls OPTIONS as a business endpoint, evaluate it separately.

**`setAllowedHeaders(…)`:** permits the request header names listed by the browser in `Access-Control-Request-Headers`. It does not validate the value of `Authorization` or a CSRF token. If the frontend uses `X-Request-ID`, it must be intentionally added to the list.

**`setExposedHeaders(…)`:** adds response headers that JavaScript is allowed to read, for example `Location`. This is the **response** direction, completely distinct from `allowedHeaders` on the request direction.

**`setAllowCredentials(true)`:** permits credentialed CORS responses when the browser wants to send cookies/credentials. The client must also set `credentials: "include"`, and cookies remain subject to `SameSite`, `Secure`, domain/path, and third-party cookie policies. Do not set `true` if the flow does not need credentials.

**`setMaxAge(3600L)`:** suggested preflight cache duration for the browser, in seconds. It does not cache user access permissions; the browser may enforce its own cap.

**`registerCorsConfiguration("/api/**", policy)`:** binds the policy by path. Endpoints outside `/api/**` (such as a login endpoint if placed at `/login`) do not automatically receive this policy; you must account for the paths the frontend actually uses.

### Wildcards and Credentials

Avoid this combination:

~~~java
// Example that is INVALID / should not be used for credentials:
policy.setAllowedOrigins(List.of("*"));
policy.setAllowCredentials(true);
~~~

When credentials are enabled, browsers do not accept `Access-Control-Allow-Origin: *` as valid CORS approval. Spring also validates this configuration combination. Use an explicit origin allowlist. `setAllowedOriginPatterns(…)` supports patterns and can echo back the matched origin, but the pattern must be narrow and genuinely trusted; an overly broad wildcard can allow unwanted origins to read user data.

## 5. When Does Spring Security Automatically Pick Up `CorsConfigurationSource`?

There are three common ways to set this up.

### 5.1. Passing the Source Explicitly

In the Section 4 example, the `UrlBasedCorsConfigurationSource` bean is injected into `SecurityFilterChain` and passed directly to `.cors(…)`. This makes the code explicit about which policy serves which chain, useful when the application is complex or has multiple sources.

### 5.2. Using the Default Configuration When a Suitable Bean Exists

When a suitable `UrlBasedCorsConfigurationSource` bean exists, Spring Security can integrate it via:

~~~java
.cors(Customizer.withDefaults())
~~~

Important point: if there are **multiple `CorsConfigurationSource` beans**, Spring Security cannot automatically determine which bean to use. In that case, configure the CORS source for each chain using `cors.configurationSource(…)` rather than hoping the framework guesses right.

### 5.3. Spring MVC CORS Integration

If the application uses Spring MVC and has no dedicated `CorsConfigurationSource`, Spring Security can use the MVC CORS policy when `.cors(Customizer.withDefaults())` is enabled. MVC configuration can come from `WebMvcConfigurer` or `@CrossOrigin` on controllers.

However, `@CrossOrigin` on a controller does not by itself fix all cases where preflight is blocked by a security filter. Avoid maintaining different allowlists in controllers, MVC global config, Security source, and gateway without knowing which policy actually applies. Choose a clear integration path and test actual paths.

## 6. Multiple `SecurityFilterChain` Beans and Path-Based Policies

If an application has multiple filter chains, the first chain matching the request determines the Spring Security configuration applied. For example, `/api/**` APIs and `/**` web pages may use different authentication mechanisms. CORS must be configured in the **chain that receives both OPTIONS and actual requests**.

The snippet below illustrates only an additional bean in an **alternative** configuration; do not place it alongside the catch-all `SecurityFilterChain` from Section 4 without reorganizing matchers and chain ordering:

~~~java
@Bean
@org.springframework.core.annotation.Order(1)
SecurityFilterChain apiChain(
        HttpSecurity http,
        org.springframework.web.cors.CorsConfigurationSource source)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .cors(cors -> cors.configurationSource(source))
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(
            org.springframework.security.config.Customizer.withDefaults())
        .build();
}
~~~

This snippet illustrates attaching a source to the **right chain**; it does not fully define additional beans or decide whether HTTP Basic should be used in production. If there are additional chains for other paths, their respective security/CORS configurations must be verified separately.

For different policies per path, `UrlBasedCorsConfigurationSource` can register multiple configurations:

~~~java
// Fragment inside the source creation method.
// publicPolicy/privatePolicy are two already-declared CorsConfiguration instances.
source.registerCorsConfiguration("/api/public/**", publicPolicy);
source.registerCorsConfiguration("/api/admin/**", privatePolicy);
~~~

This is an API illustration fragment, not a standalone runnable class. Even if a frontend origin is allowed by CORS to call `/api/admin/**`, the user must still be granted the admin role by **authorization**.

## 7. CORS and Other Security Layers: Do Not Confuse the Same HTTP 403

| Layer | Question answered | Typical way to detect |
| --- | --- | --- |
| CORS | Is this origin allowed to read the response and send this method/header in the browser? | Preflight 403 or response missing `Access-Control-Allow-Origin`. |
| Authentication | Which user does the request belong to? | 401 or login redirect when no valid session exists. |
| Authorization | Does the logged-in user have sufficient permissions to call the endpoint? | 403 after role/permission check. |
| Session/cookie | Did the browser actually send the cookie to the API? | `SameSite`/`Secure`/domain/path/third-party cookie policy causes cookie absence. |
| CSRF | Does the state-changing request carry a valid CSRF token? | POST/PUT/PATCH/DELETE may get 403 even though preflight passed. |

### 7.1. Preflight Succeeding While POST Fails Is Completely Possible

For example:

1. The browser sends `OPTIONS /api/items` and CORS allows `POST`, `content-type`, `x-csrf-token`.
2. The browser sends `POST /api/items`.
3. The session cookie does not reach the backend or has expired → authentication fails.
4. Or the user is logged in but missing/wrong CSRF token → `CsrfFilter` rejects it.
5. Or the token is valid but the user lacks permissions → authorization returns 403.

In all three cases above, loosening CORS permissions will not fix the root cause. You need to inspect status/headers and exceptions from the relevant backend layer.

### 7.2. Cross-Origin Differs from Cross-Site

Different ports mean different **origins**, yet they may still be **same-site**. Cross-site cookies must satisfy stricter policies; `credentials: "include"` does not force the browser to bypass `SameSite` or third-party cookie blocking. When a request is genuinely cross-site and needs cookies, you typically have to design `SameSite=None; Secure` cookies and proper HTTPS, and verify in a real browser. A CORS source does not set session cookies itself.

### 7.3. CSRF Remains Active When Using Session Cookies

If the application authenticates using cookies automatically sent by the browser, enabling CORS does not remove the need for CSRF protection. `setAllowedHeaders(List.of("X-CSRF-TOKEN", …))` only allows the **header name** to be sent; the frontend must still fetch a valid token from the backend and send the right value. `csrf(Customizer.withDefaults())` in Section 4 intentionally preserves CSRF protection. For systems using Bearer tokens manually attached in `Authorization` and not relying on browser-managed credentials, the threat model may differ, yet the CSRF decision must be evaluated separately.

### 7.4. Why Isn't `requestMatchers(OPTIONS, "/**").permitAll()` Enough?

An authorization rule can let OPTIONS proceed, yet it **does not generate** `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers`. The browser may still block preflight due to missing policy headers. You should configure the CORS filter/source properly before authentication and only add an OPTIONS rule if there is genuinely a separate business requirement.

## 8. Using Browser DevTools and `curl` to Inspect

In DevTools → Network, filter by `OPTIONS` and the endpoint:

1. Confirm the request has the exact `Origin`.
2. Read `Access-Control-Request-Method` and `Access-Control-Request-Headers`.
3. Check the preflight status and response headers `Access-Control-Allow-Origin`, `-Methods`, `-Headers`, `-Credentials`.
4. Determine whether the actual request ran after preflight; if so, inspect the actual request's response separately.
5. Verify whether cookies were sent, whether session/CSRF are valid, and whether a gateway/proxy modified response headers.

To send a preflight from a Linux/macOS terminal:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

On PowerShell, you can use `curl.exe` on one line:

~~~powershell
curl.exe -i -X OPTIONS "http://localhost:8080/api/items" -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

With the Section 4 policy, the expected response is a successful preflight (typically HTTP 200), `Access-Control-Allow-Origin: http://localhost:5173`, POST method allowed, and header names accepted. Header ordering and representation may vary across servers.

Try an origin not in the allowlist:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"
~~~

With the common default Spring processor, an invalid preflight typically returns 403. **Do not infer** that non-browser clients cannot call the API: `curl` only inspects server headers and does not enforce the browser's Same-Origin Policy.

Do not look only at the HTTP status. A 200 preflight without a matching `Access-Control-Allow-Origin` is still a failure for the browser. Conversely, an actual request returning 403 may be due to CSRF/auth rather than a CORS policy issue.

## 9. Integration Testing with MockMvc

Add test dependencies `spring-boot-starter-test` and `org.springframework.security:spring-security-test`. The test below uses the project and controller from Section 4, verifying allowed preflight, unauthorized origin, actual GET with CORS header, and POST still enforcing CSRF protection. The test uses `MockMvc` so no browser is needed, yet it does not replace testing cookie policies in a real browser.

**`src/test/java/com/example/corsdemo/CorsIntegrationTest.java`:**

~~~java
package com.example.corsdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsIntegrationTest {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightWorksWithoutLogin() throws Exception {
        mvc.perform(options("/api/items")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void untrustedPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/items")
                .header(HttpHeaders.ORIGIN, "https://untrusted.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void actualGetHasCorsHeader() throws Exception {
        mvc.perform(get("/api/hello")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND));
    }

    @Test
    void corsDoesNotDisableCsrf() throws Exception {
        mvc.perform(post("/api/items")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Book\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/items")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Book\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND));
    }
}
~~~

Run via the wrapper of the **Spring Boot project with all dependencies**, for example `./gradlew test` on Linux/macOS or `.\gradlew.bat test` on Windows. In the tests, `.with(user("alice"))` creates a mock user for Spring Security, and `.with(csrf())` adds a valid token for MockMvc. If you only test preflight without testing the actual POST, you will miss cookie, authentication, or CSRF errors. If you only test POST and skip preflight, the browser may block before that request ever exists.

What to observe:

| Test | Expected result | Proves |
| --- | --- | --- |
| OPTIONS from allowlisted origin | Preflight 200 and appropriate CORS headers | Policy permits method/headers before authentication. |
| OPTIONS from untrusted origin | Rejected by CORS, usually 403 | Origin allowlist is in effect. |
| Authenticated GET with Origin | 200 and `Access-Control-Allow-Origin` | Actual response can be read by the browser. |
| Authenticated POST missing CSRF | 403 | CORS does not replace CSRF protection. |
| Authenticated POST with CSRF | 201 from controller | CORS, authentication, and CSRF work together. |

## 10. Customizing When Requirements Get More Complex

### 10.1. One Policy per API Group

A `UrlBasedCorsConfigurationSource` can register multiple paths:

~~~java
// Fragment inside the source creation method, not a standalone class.
// publicPolicy and adminPolicy are previously created CorsConfiguration instances.
source.registerCorsConfiguration("/api/public/**", publicPolicy);
source.registerCorsConfiguration("/api/admin/**", adminPolicy);
~~~

This is **URL-based policy**. CORS does not decide whether an account has admin permissions; the backend must use authorization. You must test which path pattern actually matches each request.

### 10.2. Multiple Frontends by Environment

Place production/dev origins in controlled environment configuration to avoid accidentally allowing dev origins in production. Do not reflect arbitrary `Origin` values from requests into `Access-Control-Allow-Origin` with credentials enabled, because that amounts to a policy allowing every origin to read session data.

`setAllowedOriginPatterns(…)` permits patterns like subdomains, yet can open broader access than intended. Only use it if you trust **every matched subdomain**; subdomains hosted by third parties may not share the same trust level. With a few fixed frontends, an exact allowlist is easier to audit.

### 10.3. Custom Source per Tenant

If CORS policy must depend on tenant, you can implement `CorsConfigurationSource` yourself or select a policy from a trusted configuration source. You must validate tenant and origin using verified server-side data; never let the client pass an "allowed tenantId/origin" and use it directly to grant CORS permission. Caching, tenant changes, and uncredentialed preflights must be considered when designing the resolver.

### 10.4. Gateway or Reverse Proxy

If a gateway/CDN already answers preflights or adds CORS headers itself, align on which layer owns responsibility. Duplicate or conflicting headers (for example proxy adds `*`, Spring adds a specific origin) can cause browser rejection. If a request never reaches the Servlet app, editing `CorsConfigurationSource` in Spring does not affect error responses at the gateway.

### 10.5. APIs Not Using Cookies

If the API only uses tokens explicitly sent in `Authorization` and does not need credentialed CORS under browser policy, consider stricter credentials configuration; do not enable it on every route out of habit. The CSRF decision depends on the overall authentication mechanism, not merely whether CORS is present.

## 11. Diagnostic Table for Typical Integration Errors

| Symptom | Cause to verify | Remedy |
| --- | --- | --- |
| `OPTIONS` returns 401 or redirects to login | Does the security chain run CORS before authentication? | Enable `http.cors(…)` on the right chain and pass the right source. |
| `OPTIONS` 403 | Origin, requested method/header, or path mapping not covered by policy. | Check `Origin`, `Access-Control-Request-*`, and actual policy. |
| Browser reports missing `Access-Control-Allow-Origin` | Request did not pass through CORS processing or endpoint is outside `/api/**`. | Identify chain/path/gateway, add properly scoped policy. |
| Cookies not sent | Cross-site cookie policy, `SameSite`, `Secure`, domain/path, `credentials`. | Check browser Network/cookies; fix cookie/session config. |
| Preflight passes yet POST 403 | Missing/invalid CSRF token or user lacks permission. | Inspect security exception; do not broaden CORS blindly. |
| Browser reports wildcard origin + credentials | Using `*` with credentials or proxy adding wildcard. | Use explicit origins, remove conflicting headers. |
| GET works yet JSON POST fails | POST/content-type/new header triggers preflight not yet allowed by policy. | Add the legitimately needed method/header. |
| `@CrossOrigin` placed on controller yet preflight still fails | Security filter blocks before controller/MVC. | Wire CORS into the security chain before authentication. |
| Multiple `CorsConfigurationSource` beans | Framework cannot auto-detect the source for the chain. | Specify `cors.configurationSource(…)` explicitly. |
| Works locally, fails in production | Scheme/host/port, proxy, credential cookies differ by environment. | Compare request/response headers and corresponding source. |
| MockMvc passes, browser fails | Test does not simulate full browser cookie/cross-site policies. | Test end-to-end on the real origin and deployed HTTPS. |

A safe debugging workflow:

1. Identify the exact frontend origin and request path.
2. Determine whether there is a preflight; read the requested method and headers.
3. Identify the `SecurityFilterChain` receiving `OPTIONS` and the actual request.
4. Identify which policy `CorsConfigurationSource` returns; does it return null?
5. Check the HTTP status **together with** `Access-Control-Allow-*` on preflight and actual response.
6. Once CORS is correct, move on to authentication/session/CSRF/authorization.
7. Check gateway/proxy and caching; `Vary: Origin` helps caches distinguish responses by origin when applicable.

Do not log raw session cookies, CSRF tokens, Authorization headers, or sensitive user data just to debug CORS.

## 12. Common Misconceptions

**"Adding `@CrossOrigin("*")` is enough."** It does not guarantee preflight is processed before security filters; a wildcard cannot be used for credentials approval when credentials are enabled. Choose a verified CORS source and filter order.

**"`CorsConfigurationSource` is the CORS filter itself."** The source only **provides the policy**; the filter/processor handles requests and responses.

**"Setting `OPTIONS permitAll()` solves it."** An authorization rule does not generate the `Access-Control-Allow-*` headers required by the browser.

**"If preflight is 200, POST must be 200."** The actual request still must pass cookies, authentication, CSRF, authorization, and the controller; 401/403/other 4xx codes can be completely valid.

**"With CORS, CSRF is not needed."** CORS governs cross-origin response sharing; CSRF evaluates state-changing requests when the browser automatically sends credentials. The two mechanisms complement each other.

**"CORS blocks all external clients."** CORS is enforced primarily by browsers; direct calls via HTTP clients are not subject to the same Same-Origin Policy. The backend needs its own authentication and authorization.

**"Having `Authorization` in allowedHeaders means the token has been checked."** No. Allowed headers are only the list of header names the browser may send; the token inside must still be verified by the backend.

**"Configuring CORS on one chain automatically applies to all chains."** Each request enters the chain that matches it; policy must be attached in the right place and for the right paths.

## 13. Thought Exercises and Answers

1. **Frontend changes from `localhost:5173` to `localhost:5174`; why does preflight fail?** The origin changed port so it no longer matches the allowlist; update allowed origins if it is a trusted frontend.
2. **Preflight requests `content-type,x-csrf-token`, policy only allows `Content-Type`; what happens?** The browser is not allowed to use the missing header; declare the CSRF header actually used.
3. **The controller receives `POST /api/items` when curl calls it, yet the browser shows no POST after OPTIONS: where to look?** Check the preflight response, path mapping, requested method/headers, chain, and proxy before debugging the controller.
4. **Preflight passes, POST gets 403 due to invalid CSRF: do we need `allowedOrigins("*")`?** No; fix the flow for obtaining and submitting the CSRF token.
5. **Two `CorsConfigurationSource` beans exist, and the API chain needs a specific one: how?** Inject the right source and use `.cors(cors -> cors.configurationSource(source))` on the API chain.
6. **Frontend needs to read `Location` on a 201 response: put it in `allowedHeaders` or `exposedHeaders`?** Put it in `exposedHeaders`, because `Location` is a response header.
7. **Why test in a real browser even when MockMvc passes?** MockMvc does not execute the full browser cookie policy, preflight cache, and cross-site behavior outside Spring MVC.
8. **Why shouldn't we use the client-sent Origin to build a policy for that Origin itself?** A client can pick any origin; unconditional reflection turns an allowlist into allowing everyone.

**Conclusion:** `CorsConfiguration` describes *what is allowed*; `CorsConfigurationSource` decides *which policy applies to a request*; `HttpSecurity.cors(…)` and CORS processing enforce the policy at the right position in the Servlet security chain. To integrate cleanly, configure an allowlist of origins/methods/headers as required, let preflight pass through the CORS layer, and test the actual requests with authentication, cookies, and CSRF.