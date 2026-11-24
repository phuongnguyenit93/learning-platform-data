# CORS Does Not Grant Business Permissions and Does Not Block Non-Browser Clients

> **Module:** Spring Security - fundamentals  
> **Parent topic:** CORS  
> **Core thesis:** CORS is a mechanism combining **HTTP headers and browser-enforced policy** to control whether JavaScript at origin A can read responses from origin B. CORS **is not authentication, is not business authorization, is not a firewall**, and cannot be relied upon to stop clients such as `curl`, Postman, scripts, or backend services from calling an API.

## 1. Learning objectives

After this lesson, you will be able to:

- Explain **origin** and **same-origin policy** accurately, distinguishing scheme/host/port.
- Describe the flow of a **simple CORS request** and an **OPTIONS preflight**; understand when the actual request has already been sent to the server even if the script is blocked from reading the response.
- Distinguish `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Expose-Headers`, and `Vary`.
- Explain why an allowed origin does not mean a user has permission to read reports, modify orders, make payments, or access another tenant.
- Demonstrate that a **non-browser** client can still send HTTP requests to an API; the `Origin` header is not trustworthy proof of identity.
- Configure Spring Boot 3.3.5, Java 17, and Spring Security 6.x: CORS accepts only one frontend, the API still demands authentication + authorities, and browser POSTs still require CSRF tokens.
- Write MockMvc tests separating CORS failures, authentication failures, missing-permission failures, and CSRF failures.
- Design server-side controls based on principal, scopes/roles, resource ownership, tenant, and business policies.

## 2. What does CORS actually do?

**Cross-Origin Resource Sharing (CORS)** is a mechanism using HTTP headers by which a server indicates whether a browser may allow a web page/script from another origin to use a response. CORS adds controlled sharing on top of the browser's **same-origin policy**.

For example:

~~~text
Open UI page:
  https://ui.example.test

JavaScript fetch:
  https://api.example.test/reports/7

The two URLs are cross-origin because their hostnames differ.
The browser uses CORS to determine whether scripts from the UI
may read the response returned by the API.
~~~

For `fetch()` or `XMLHttpRequest` running in a browser, CORS is an important part of protecting cross-origin data. However, **an API server must not treat the browser blocking a response as proof that the client was authenticated or denied business permissions**.

A client like `curl` sends HTTP requests directly and reads responses straight from its TCP/TLS connection. It has no obligation to enforce the same-origin policy like a browser. Therefore:

~~~text
Browser JS from a disallowed origin:
  May be denied access to the response by the browser.

curl / Postman / backend service:
  Can still send the HTTP request.
  The response is received directly by that client if the server processes it.

In both cases:
  The server MUST still authenticate and authorize.
~~~

**Important:** A Spring CorsFilter or reverse proxy may actively return `403` for requests **carrying a disallowed Origin header**. That does not turn CORS into a network barrier against all clients: a non-browser client can omit `Origin`, send a different value, and the server must still enforce security policies independently.

## 3. Origin consists of scheme, host, and port

An origin is determined by the tuple:

~~~text
scheme + host + port
~~~

For example, the origin of `https://app.example.test:8443/dashboard` is `https://app.example.test:8443`. The path `/dashboard` is **not** part of the origin.

| URL | Compared to `https://app.example.test` |
| --- | --- |
| `https://app.example.test/page2` | Same origin (different path) |
| `https://app.example.test:443` | Same origin per default HTTPS port |
| `http://app.example.test` | Cross-origin (different scheme) |
| `https://api.example.test` | Cross-origin (different host) |
| `https://app.example.test:8443` | Cross-origin (different port) |
| `https://app.example.test:3000` | Cross-origin (different port) |

**Origin and site are two distinct concepts.** Two subdomains can be same-site under the SameSite cookie model yet remain cross-origin for CORS. Do not use the phrase “same domain” without specifying scheme, host, and port.

CORS primarily governs browsers when a web page needs to read a response from another origin. It does not state that cross-origin requests are forbidden on the network.

## 4. Simple requests and preflight requests

### 4.1. Simple cross-origin request

Some requests, such as a `GET` with permitted headers, may require no preflight. The browser still **sends the actual request** to the server. If the response lacks matching CORS headers, the browser will not expose the response to the JavaScript calling `fetch()`.

~~~text
Browser JS origin https://ui.example.test
       |
       | GET https://api.example.test/public-news
       | Origin: https://ui.example.test
       v
API may process the request and return HTTP 200
       |
       | Missing matching Access-Control-Allow-Origin
       v
Browser BLOCKS script from reading response
       |
       v
API already received and processed the GET!
~~~

This is especially critical for **side-effecting requests**: you cannot say “CORS protects accounts from CSRF” when certain cross-origin requests can actually reach the server and cause effects even though the script cannot read the response.

**Never place state changes on GET**. A system using `GET /delete?id=42` violates HTTP safe-method assumptions and risks being triggered through multiple mechanisms without JavaScript needing to read the response.

### 4.2. OPTIONS preflight

For certain methods/headers/content types, the browser sends a **preflight** before the actual request:

~~~http
OPTIONS /reports/7 HTTP/1.1
Host: api.example.test
Origin: https://ui.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: Authorization
~~~

The server returns CORS details to the browser, for example:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
~~~

If preflight is rejected, the browser normally **does not send the actual request** in that preflight flow. However, preflight only asks whether the browser may use the cross-origin method/headers; it **does not prove an authenticated principal** and grants no resource permissions.

**Preflight sends no credentials such as session cookies under the Fetch standard.** Spring Security recommends processing CORS before the authentication/filter chain, because if the application demands a session cookie right on OPTIONS, preflight will be rejected as an unauthenticated request. Do not “fix” preflight errors with `permitAll("/**")` for all actual requests.

### 4.3. An accepted preflight does not mean the subsequent POST will succeed

~~~text
OPTIONS /reports
  Origin: https://ui.example.test
  Access-Control-Request-Method: POST
  -> CORS OK (browser may send POST)

POST /reports
  Authorization: Bearer ...
  X-CSRF-TOKEN: ...
  -> must still pass authentication
  -> must still pass authorization
  -> must still pass CSRF when applicable
  -> must still pass object/business policy
~~~

A browser may be permitted to **send/read cross-origin responses**, yet the user account still cannot create a report if it lacks `report:create`.

## 5. CORS headers are not security roles

| Header | Function | What it does NOT mean |
| --- | --- | --- |
| `Origin` | Browser tells server the caller web context's origin | Not a JWT, username, user ID, or trustworthy credential |
| `Access-Control-Allow-Origin` | Origin the browser allows to read the response | Does not prove caller has permission for the resource |
| `Access-Control-Allow-Credentials` | Tells browser whether a credentialed request's response may be shared in the CORS flow | Does not validate cookies/JWTs and grants no permissions |
| `Access-Control-Allow-Methods` | HTTP methods the browser may use per CORS policy | Does not replace `@PreAuthorize` or method authorization |
| `Access-Control-Allow-Headers` | Request headers the browser may use in a cross-origin request | Does not prove the header holds a valid token |
| `Access-Control-Expose-Headers` | Response headers JS may read beyond the safelist | Does not grant business permissions |
| `Access-Control-Max-Age` | Hints how long the browser may cache preflight results | Does not extend credential lifetime |
| `Vary: Origin` | Helps shared caches avoid mixing response variants across Origins | Not access permission or authentication |

The server must distinguish an **allowed origin** from an **authorized user**. Origin usually represents a web application/site, not a user or tenant.

### Credentialed requests require strict configuration

When a browser sends a cross-origin request with credentials (e.g. `fetch(..., { credentials: "include" })`), the response must not use `Access-Control-Allow-Origin: *` for JavaScript to read the credentialed response. The server must allow **specific origins** and set `Access-Control-Allow-Credentials: true` where appropriate.

**Avoid arbitrarily “reflecting” every Origin** just to clear CORS errors, especially when credentials are enabled. Reflecting origins without allowlist validation lets virtually any site read cookie-authenticated responses, creating a severe data-leak risk.

Even with explicit origins, you still need authentication, roles/authorities, and object-level authorization.

## 6. How does CORS differ from authentication, authorization, CSRF, and network security?

| Mechanism | Question it answers | Example |
| --- | --- | --- |
| **CORS** | May a browser script at origin A read a response from origin B? | `Access-Control-Allow-Origin` |
| **Authentication** | Does the request carry a valid identity/credential? | Session login, OAuth2 bearer, HTTP Basic |
| **Authorization** | Is this principal allowed to perform this action on this resource? | `hasAuthority("report:read")`, tenant policy |
| **CSRF protection** | Does a request using browser auto-credentials show intentional proof from a valid source? | CSRF token in form/header |
| **Network policy** | Can the client open a connection to the server? | Firewall, VPC, network allowlist, mTLS |
| **Rate limiting** | Is the client/identity sending too many requests? | Quotas, request rates, abuse detection |
| **Input validation** | Does request data match schemas and business rules? | Bean Validation, domain validation |

Never use a CORS allowlist in place of a backend access-control list. CORS does not prevent:

- `curl`, Postman, Python `requests`, or SDKs calling the API.
- Non-browser server-to-server calls.
- An attacker using leaked credentials/tokens (unless server authentication/authorization rejects them).
- A logged-in user from an allowed origin who lacks permission on another user's report.
- A same-origin browser client calling the API with the current account's permissions.
- Simple cross-origin CSRF requests under conditions where cookies are auto-sent.

**Threats do not vanish just because DevTools shows “blocked by CORS policy”.** The server may have already received and executed the request, or sent a response that JavaScript simply cannot read.

## 7. Business permission example: reading another tenant's report

Suppose frontend `https://ui.example.test` is allowed to call the API. Alice logs in successfully, holds `report:read`, and belongs to tenant A; report 77 belongs to tenant B.

~~~text
CORS:
  Origin=https://ui.example.test -> ALLOWED

Authentication:
  Alice has a valid token/session -> AUTHENTICATED

Authority:
  Alice has report:read -> TRUE

Object-level authorization:
  report 77 belongs to tenant B, Alice belongs to tenant A -> DENY

Expected outcome: Do not disclose report 77.
~~~

Passing CORS and passing authority checks are still **not enough** when policies enforce resource/owner/tenant authorization.

A service layer can use Spring method security:

~~~java
// ILLUSTRATIVE SNIPPET in a Spring-managed service.
// Requires the application's real reportPolicy bean and repository.
@PreAuthorize(
    "hasAuthority('report:read') and " +
    "@reportPolicy.canRead(authentication, #reportId)"
)
public Report findReport(long reportId) {
    return repository.findById(reportId).orElseThrow();
}
~~~

This is integration code, **not a standalone class**. `reportPolicy` must verify owner/tenant using server-trusted data, never relying on a client-supplied `tenantId`. `@EnableMethodSecurity` must be enabled in the Spring context, and calls must pass through the Spring bean proxy/advice for `@PreAuthorize` to take effect.

**Never base policy on comparing `Origin` against a tenant name.** One valid origin can serve multiple users/tenants, and non-browser clients can spoof `Origin`.

## 8. Proving with `curl`: Origin is not a credential

Suppose the server allows CORS from `https://ui.example.test`, and route `GET /reports/7` requires an authenticated principal with `report:read`.

A client such as `curl` can send:

~~~bash
# No Origin sent; this is a normal HTTP request.
curl -i -u alice:demo-pass http://localhost:8080/reports/7

# Keeping valid credentials while attaching a disallowed Origin:
curl -i -u alice:demo-pass \
  -H 'Origin: https://untrusted.example.test' \
  http://localhost:8080/reports/7

# Can alter or omit the Origin header when crafting requests manually:
curl -i -u alice:demo-pass \
  -H 'Origin: https://ui.example.test' \
  http://localhost:8080/reports/7
~~~

In the Spring Boot example below, the first request **can return 200** because HTTP Basic authentication and `report:read` are valid, even with no CORS header in the request. The second request may receive 403 from Spring's CorsFilter **because it explicitly declared a disallowed Origin**. The third request can also return 200 with CORS headers if credentials are valid.

Takeaways:

- The `Origin` header **does not prove** the request actually came from code running at that origin.
- `curl` is not a browser and has no reason to enforce the same-origin policy; it chooses whichever HTTP headers to send.
- Server-side CORS processing can reject requests carrying an invalid Origin, yet it is not a network mesh blocking all clients.
- What truly protects the report is **authentication + authorization**; without valid credentials, `curl` cannot access protected routes.

Do not interpret `curl` omitting `Origin` as a recommendation to bypass controls. It is solely a theoretical demonstration that CORS **is not an API access-control mechanism**.

## 9. Spring Boot 3.3.5 / Java 17 example: independent CORS and business permissions

Demo application goals:

1. Accept cross-origin browser requests **only** from `https://ui.example.test`.
2. Allow that frontend to send `Authorization`, `Content-Type`, and `X-CSRF-TOKEN` headers.
3. Only users with `report:read` may GET `/reports/{id}`.
4. Only users with `report:create` and a valid CSRF token may POST `/reports`.
5. Keep `GET /public` public.
6. Prove that an accepted preflight **does not** mean the actual request is authorized.
7. Prove that requests without Origin are still governed by server policy.

**Learning versions:** Java 17+, Gradle 8.x, Spring Boot 3.3.5, Spring Security 6.x. Code uses Servlet/Spring MVC and MockMvc, **not WebFlux**.

### 9.1. Project structure

~~~text
cors-authz-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/cors/
    │   ├── CorsAuthzApplication.java
    │   ├── SecurityConfig.java
    │   └── ReportController.java
    └── test/java/demo/cors/
        └── CorsAndAuthorizationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'cors-authz-demo'
~~~

File `build.gradle`:

~~~groovy
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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` provides Spring MVC/Tomcat; `spring-boot-starter-security` provides Spring Security; the two test starters provide JUnit, MockMvc, and `@WithMockUser`. `spring-boot-starter-security` does not automatically establish the right business authorization policy for the app; we declare it explicitly below.

### 9.2. Main application

File `src/main/java/demo/cors/CorsAuthzApplication.java`:

~~~java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsAuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsAuthzApplication.class, args);
    }
}
~~~

### 9.3. Spring Security: CORS for browsers + authz for all HTTP clients

File `src/main/java/demo/cors/SecurityConfig.java`:

~~~java
package demo.cors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Explicit origin; DO NOT use "*" with credentialed browser requests.
        cors.setAllowedOrigins(List.of("https://ui.example.test"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/reports/**"
                ).hasAuthority("report:read")
                .requestMatchers(
                    HttpMethod.POST, "/reports"
                ).hasAuthority("report:create")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF remains enabled for browser POSTs.
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-pass"))
            .authorities("report:create")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

**Layer-by-layer explanation:**

- `corsConfigurationSource()` declares browser origins, methods, and headers allowed for CORS. It **does not specify** who can view reports.
- `http.cors(...)` integrates Spring Security with CORS processing so preflight runs before authentication. With the `UrlBasedCorsConfigurationSource` bean, Spring Security has full CORS configuration.
- `GET /public` is `permitAll()` because it requires no identity, not because CORS checked it.
- `GET /reports/**` requires `report:read`; `POST /reports` requires `report:create`; unlisted routes default to `denyAll()`.
- `httpBasic(...)` provides a real authentication mechanism for the demo and `curl` commands. Production must use HTTPS and an appropriate auth mechanism, never putting real passwords in scripts/logs.
- `csrf(Customizer.withDefaults())` keeps CSRF enabled; a POST request authorized to create reports still needs a token in this browser application context.
- `setAllowCredentials(true)` illustrates a UI requiring credentialed cross-origin behavior; **only** explicit origins are permitted. Real cookies still obey SameSite/Secure/Path/Domain and browser policies.
- `setAllowedMethods(...)` is **CORS negotiation**, not a replacement for authorizeHttpRequests; even though POST is allowed by CORS, Alice still lacks `report:create`.

### 9.4. Controller with observable report-creation state

File `src/main/java/demo/cors/ReportController.java`:

~~~java
package demo.cors;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final AtomicInteger created = new AtomicInteger();

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/reports/{id}")
    public String readReport(@PathVariable long id) {
        return "report:" + id;
    }

    @PostMapping("/reports")
    public ResponseEntity<String> createReport() {
        int id = created.incrementAndGet();
        return ResponseEntity.status(HttpStatus.CREATED)
            .body("created:" + id);
    }

    public int createdCount() {
        return created.get();
    }

    public void resetForTest() {
        created.set(0);
    }
}
~~~

`AtomicInteger` is a **simulated side effect** helping tests detect unauthorized mutations. This API does not persist reports to a database and does not implement owner/tenant checks; we deliberately separated them to show that CORS and authority checks are distinct mechanisms. Production requires resource-level policies as in section 7.

### 9.5. MockMvc tests: distinguishing each rejection layer

File `src/test/java/demo/cors/CorsAndAuthorizationTest.java`:

~~~java
package demo.cors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAndAuthorizationTest {

    private static final String UI = "https://ui.example.test";
    private static final String OTHER =
        "https://untrusted.example.test";

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportController reports;

    @BeforeEach
    void reset() {
        reports.resetForTest();
    }

    @Test
    void publicEndpointDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void allowedPreflightNeedsNoLogin() throws Exception {
        mvc.perform(options("/reports/7")
                .header(HttpHeaders.ORIGIN, UI)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, UI
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"
            ));
    }

    @Test
    void disallowedPreflightIsRejectedByCors() throws Exception {
        mvc.perform(options("/reports/7")
                .header(HttpHeaders.ORIGIN, OTHER)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginWithoutAuthenticationIsStillRejected()
            throws Exception {
        mvc.perform(get("/reports/7")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:create")
    void allowedOriginWithoutReadPermissionIsStillForbidden()
            throws Exception {
        mvc.perform(get("/reports/7")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void allowedOriginWithReadPermissionWorks() throws Exception {
        mvc.perform(get("/reports/7")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isOk())
            .andExpect(content().string("report:7"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, UI
            ));
    }

    @Test
    void validBasicRequestWithoutOriginIsAuthorized()
            throws Exception {
        // Simulate an HTTP client that sends no Origin.
        mvc.perform(get("/reports/7")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:7"));
    }

    @Test
    void untrustedOriginHeaderGetsCorsRejection()
            throws Exception {
        mvc.perform(get("/reports/7")
                .with(httpBasic("alice", "demo-pass"))
                .header(HttpHeaders.ORIGIN, OTHER))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:create")
    void postMissingCsrfCannotMutate() throws Exception {
        mvc.perform(post("/reports")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isForbidden());

        assertEquals(0, reports.createdCount());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:create")
    void postWithCsrfAndCreatePermissionWorks() throws Exception {
        mvc.perform(post("/reports")
                .header(HttpHeaders.ORIGIN, UI)
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:1"));

        assertEquals(1, reports.createdCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void postWithCsrfButWithoutCreatePermissionIsRejected()
            throws Exception {
        mvc.perform(post("/reports")
                .header(HttpHeaders.ORIGIN, UI)
                .with(csrf()))
            .andExpect(status().isForbidden());

        assertEquals(0, reports.createdCount());
    }
}
~~~

**Expected result:** all **11 tests pass** when run with the dependencies/configuration above. These results are **inferred from the example code**, not an executed test log in this lesson.

Run from the project root using JDK 17+ and Gradle 8.x:

~~~bash
gradle test
~~~

### 9.6. Evidence table from tests

| Test/condition | Expected | Conclusion |
| --- | --- | --- |
| `GET /public` | 200 | Public endpoint requires no login |
| OPTIONS preflight from valid UI | 200 + `Access-Control-Allow-Origin` | Browser is permitted to attempt cross-origin actual GET |
| OPTIONS preflight from another origin | 403 | CORS config rejects declared origin |
| Actual GET from valid UI without authentication | 401 | Passing CORS **does not log the user in** |
| Actual GET from valid UI, Bob only has `report:create` | 403 | Passing CORS **does not grant read permission** |
| Actual GET from valid UI, Alice has `report:read` | 200 | Authz determines report read permission |
| GET without Origin, valid Basic Alice | 200 | Non-browser-style requests are still processed by server |
| GET with unknown Origin, valid Basic Alice | 403 | Spring CORS processor rejects declared Origin |
| Bob's POST with valid Origin, missing CSRF | 403, counter 0 | CORS/authz do not replace browser CSRF |
| Bob's POST with CSRF and `report:create` | 201, counter 1 | Satisfies all protection layers |
| Alice's POST with CSRF but without `report:create` | 403, counter 0 | Passing CSRF does not grant business authority |

**Do not interpret the “Unknown Origin → 403” test as “no external client can call it”.** The “No Origin + valid Basic → 200” test demonstrates that exact boundary. Depending on server/proxy, a non-browser request can even supply a valid `Origin`; Origin is not a credential.

`@WithMockUser` mocks the `SecurityContext` to focus on testing authorization; it does not verify real Basic login. The `validBasicRequestWithoutOriginIsAuthorized` test uses `httpBasic(...)` to exercise the authentication filter and demo UserDetailsService.

### 9.7. Testing directly with `curl`

Run the application:

~~~bash
gradle bootRun
~~~

In another terminal:

~~~bash
# No Origin, yet Alice's Basic auth is valid -> expect 200.
curl -i -u alice:demo-pass http://localhost:8080/reports/7

# No credentials -> expect 401.
curl -i http://localhost:8080/reports/7

# Bob has valid credentials yet lacks read permission -> expect 403.
curl -i -u bob:demo-pass http://localhost:8080/reports/7

# Valid Origin and user has permission -> expect 200, with CORS headers.
curl -i -u alice:demo-pass \
  -H 'Origin: https://ui.example.test' \
  http://localhost:8080/reports/7

# Attach disallowed Origin -> CorsFilter may return 403.
curl -i -u alice:demo-pass \
  -H 'Origin: https://untrusted.example.test' \
  http://localhost:8080/reports/7

# Manually send OPTIONS preflight from UI origin:
curl -i -X OPTIONS http://localhost:8080/reports/7 \
  -H 'Origin: https://ui.example.test' \
  -H 'Access-Control-Request-Method: GET'
~~~

The final result is expected to be status 200 and `Access-Control-Allow-Origin: https://ui.example.test`. `curl` printing headers is not because it needs CORS to read the response, but because we explicitly sent a request containing CORS headers.

**Note:** `curl -u` is for local demos only to avoid exposing passwords in command history/telemetry; production should use HTTPS and secure credential handling.

### 9.8. Browser `fetch` example

JavaScript from `https://ui.example.test`:

~~~javascript
const response = await fetch("https://api.example.test/reports/7", {
  method: "GET",
  credentials: "include"
});
if (!response.ok) {
  throw new Error("API returned " + response.status);
}
console.log(await response.text());
~~~

**This example assumes** real frontend/backend deployments with proper hostnames, cookies, and an authenticated user. The local Spring Boot demo only runs on `localhost:8080`; there is no UI server or OP at `.example.test`. In browsers, `credentials: "include"` and `Access-Control-Allow-Credentials: true` only satisfy the CORS credentialed-response sharing step. Cookie `SameSite`, `Secure`, third-party cookie policies, and authentication still decide which cookies are sent.

If a browser request lacks valid authentication, the server returns 401 regardless of allowed origin. If the user lacks authority, the server returns 403 even when CORS is completely valid.

## 10. CORS and CSRF: not interchangeable

CORS generally controls **whether a browser script can read a cross-origin response**. CSRF controls **whether a state-changing request sent by the browser with auto-attached credentials reflects the user's intent**.

Example of an application using session cookies:

~~~text
Alice logs in -> Browser has JSESSIONID
Alice visits malicious page -> Page submits cross-site form POST

Browser may send POST with cookie per cookie policy,
even though the malicious page cannot read the response.

If the server does not verify a CSRF token, the command may still execute.
~~~

Therefore:

- Allowing CORS from a trusted UI **does not mean** you may disable CSRF for all POSTs.
- Blocking origins via CORS **does not guarantee** form requests are never sent.
- `SameSite` cookies help mitigate some CSRF scenarios yet do not replace all defense layers under a threat model.
- If a frontend uses only bearer access tokens explicitly placed in the `Authorization` header, with no auto-credentials and a genuinely stateless API, a different CSRF model may be evaluated; you still must protect tokens and validate issuer/audience/scope.
- If a JWT is stored in a cookie, the browser can still send it automatically: **JWT does not automatically make an app immune to CSRF**.

In the sample project, `POST /reports` requires both `report:create` and a CSRF token. Tests demonstrate that satisfying one condition does not substitute for the other.

## 11. Why must preflight be processed before authentication?

A browser preflight sends `OPTIONS`, `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` as needed. It **carries no session cookie** under the CORS preflight standard. If Spring Security demands authentication before CORS processing, the request may be treated as anonymous and return 401/403, causing the frontend to report a CORS error.

Spring Security supports:

~~~java
http.cors(Customizer.withDefaults());
~~~

with an appropriate `CorsConfigurationSource`. `CorsFilter`/CORS integration handles preflight before steps requiring an authenticated principal. **This is not a command letting all OPTIONS bypass all security**; CORS preflight is handled according to origin/method/header policy.

Do not fix preflight errors by:

~~~java
// WRONG: opening all endpoints just so OPTIONS works.
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll());
~~~

Instead, configure CORS integration and verify exact preflight status/headers. Actual GET/POST requests remain authenticated, authorized, and CSRF-protected by Spring Security.

### Why does OPTIONS sometimes return 401?

Practical causes include:

1. `http.cors(...)` was not enabled or the source could not be found.
2. A reverse proxy/gateway rejected OPTIONS before it reached the application.
3. Multiple `SecurityFilterChain` beans have different chain matchers, and the chain with CORS is not the one handling the request.
4. The path/method/header is not in the CORS allowlist.
5. A custom Servlet filter blocked the request before CORS.
6. Preflight was not recognized properly due to missing `Origin` or `Access-Control-Request-Method`.

Inspect network traces and the active filter chain before relaxing permissions on actual requests.

## 12. CORS can be enforced at multiple layers

CORS headers may be handled at:

- Spring MVC `@CrossOrigin` or `WebMvcConfigurer`.
- Spring Security `http.cors()` integrated with `CorsConfigurationSource`.
- A standalone `CorsFilter`.
- API gateway/reverse proxy/CDN.
- Platform ingress or service mesh policies.

**Avoid conflicting or duplicate CORS configurations across multiple layers.** For example, if a gateway returns `Access-Control-Allow-Origin: *` while the app returns an explicit origin, or both emit multiple header values, browsers may reject the response or unintended broad data sharing may occur.

If the API sits behind a load balancer, designate **one primary source of CORS policy**, then test both preflight and actual responses through the production entrypoint. Do not test only the service's localhost port while skipping the gateway.

### Does `@CrossOrigin` replace authz?

~~~java
// Merely CORS metadata for the controller endpoint.
@CrossOrigin(origins = "https://ui.example.test")
@GetMapping("/reports/{id}")
public String read(@PathVariable long id) {
    return "report:" + id;
}
~~~

The annotation above creates no principal, grants no authorities, checks no tenant, and does not protect service-layer data. You still need a real `SecurityFilterChain`/method security/domain policy.

If an app uses both a global CORS source and `@CrossOrigin`, understand how Spring MVC/Security combines configs; do not rely on accidental behavior.

## 13. Allowed origins, credentials, patterns, and caching

### Origin allowlist: exact and minimal

- Allow only frontends that genuinely need to call the API.
- Separate development/staging/production; never grant a wildcard to the entire Internet just for quick local testing.
- Scheme and port matter greatly: `http://localhost:3000` differs from `http://localhost:4200` and differs from `https://localhost:3000`.
- Do not include a trailing slash in origin values; an origin does not include a path.
- For multi-tenant subdomains, use controlled, carefully reviewed rules rather than allowing all untrusted or user-controlled subdomains.
- With `allowedOriginPatterns`, understand that pattern matching can produce a very broad allowlist and Spring will reflect the matched origin in responses. **Patterns do not authenticate callers**.

### Credentials: minimal as needed

If the frontend does not need cookies/client certificates or HTTP auth credentials in cross-origin flows, do not enable `allowCredentials` indiscriminately. If needed, use an explicit origin allowlist and verify browser/cookie policies. `Access-Control-Allow-Credentials: true` does not create cookies or log users in.

### CORS headers and shared caches

When `Access-Control-Allow-Origin` in responses depends on the request `Origin`, shared caches must respect `Vary: Origin` to avoid serving origin A's variant to origin B. For preflight, `Access-Control-Request-Method` and `Access-Control-Request-Headers` can also affect response variants. Depending on cache/proxy, verify proper `Vary` and cache settings.

**Do not put sensitive sessions/tokens in responses merely because the origin is allowlisted.** Enforce proper authorization and cache-control for private data.

## 14. A browser “CORS error” can mask the underlying error

In browsers, JavaScript often receives only a generic network error like “Failed to fetch”, “blocked by CORS policy”, or cannot read the status/response body, because the browser withholds cross-origin responses when policy fails to match. Root causes can include:

- The API actually returned `401 Unauthorized` while the response lacked CORS headers.
- The server returned `403 Forbidden` due to role or CSRF.
- OPTIONS preflight returned 404/405/401 from a gateway.
- `Access-Control-Allow-Origin` had the wrong scheme/port.
- Request used `credentials: include` while server returned `Access-Control-Allow-Origin: *`.
- `Access-Control-Allow-Headers` disallowed `Authorization` or `Content-Type`.
- Login redirected to another origin incompatible with the CORS flow.
- TLS certificate, DNS, mixed content, or genuine network errors.

**Debugging workflow:**

1. Open browser DevTools Network; inspect **OPTIONS preflight** and **actual request** as two distinct steps.
2. Inspect actual `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
3. Inspect response `Access-Control-Allow-Origin`, methods, headers, credentials.
4. Check HTTP status and backend/gateway logs to see whether the request reached the controller.
5. Once CORS passes, inspect authentication, authorities, CSRF, method security, and object-level policies.
6. Use `curl` to test the server directly; understand that curl does not simulate browser CORS enforcement.
7. Never “fix” issues with wildcard origins, disabling Spring Security, or switching all endpoints to `permitAll`.

A vital distinction: **`curl` returning 200 while the browser reports a CORS error** can be completely normal because `curl` is not subject to the same-origin policy, whereas the browser requires valid CORS headers. Conversely, **the browser being able to read responses** does not prove server authorization is right; an unprotected API returning data can still leak to any caller.

## 15. Non-browser clients and real API protection mechanisms

To protect an API from unauthorized clients, use backend controls:

| Requirement | Appropriate mechanism |
| --- | --- |
| Only valid users may call | Verifiable authentication: session/OAuth2 bearer/appropriate API key |
| Only authorized users may read/edit | `hasAuthority`/`hasRole`/`@PreAuthorize` and policies |
| Only resource owner or right tenant | Object-level authorization using server-trusted data |
| Service A calls Service B | OAuth2 client credentials, mTLS, or workload identity |
| Internal network access only | Firewall, private networking, network policy — does not replace user authz |
| Anti-bot/brute-force/overload | Rate limiting, quotas, monitoring, abuse detection |
| Anti-forged cookie requests | CSRF token, SameSite, and complementary layers |
| Restrict cross-origin browser JS response reading | Exact CORS allowlist |
| Prevent cross-user/cross-tenant data leaks | Query scoping + authorization at service/resource boundaries |

**The `Origin` header is not a principal.** Running `curl -H "Origin: https://ui.example.test"` does not prove the caller is a valid UI user. Authentication must verify credentials per policy; authorization must then check whether the principal has permission to perform the action on the resource.

For sensitive-privilege APIs, enforce checks at both the HTTP boundary and the domain/service boundary: for example, a job scheduler or message consumer calling a service directly will **bypass CORS**, yet still requires appropriate business policy enforcement.

## 16. Common misconceptions

| Misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| “CORS only allows website A so Postman can't call it” | Postman is not bound by browser same-origin policy | Use authentication/authorization/network controls |
| “`Access-Control-Allow-Origin` grants report-viewing permission” | It only governs browser response sharing | Use roles/authorities + object policies |
| “OPTIONS 200 means POST is authorized” | Preflight only negotiates browser method/headers, with no credentials | Check actual request via authn/authz/CSRF |
| “Browser reported CORS so the server never processed the request” | Simple requests may already have reached the server | Check network/backend logs, avoid GET side effects |
| “Use CORS instead of CSRF” | Simple cross-site requests and auto-cookies remain dangerous | Keep CSRF for session-based mutations |
| “`Origin` is a header only browsers can send” | Non-browser clients can set or omit it | Never use Origin for authentication |
| “Wildcard origin + credentials for convenience” | Browser credentialed responses reject wildcards and broad configs are dangerous | Explicit origin allowlist |
| “Adding `@CrossOrigin` secures the API” | The annotation creates no principal or business permissions | SecurityFilterChain/domain authorization |
| “Every OPTIONS must be permitAll everywhere” | Broadens access at the wrong target | Handle CORS preflight before Spring Security |
| “With JWT, CORS decides scope/role” | CORS does not verify tokens | Trusted JwtDecoder + scope/authority mapping |
| “CORS block means backend returned 403” | May be browser blocking reading a 200 response | Distinguish actual status from CORS enforcement |
| “Only testing from localhost is enough” | Skips proxy/ingress and public hostnames | Test end-to-end through gateway and multiple origins |

## 17. Required test matrix

Build a test suite covering the dimensions **origin × credentials × authority × method × CSRF**.

| Case | CORS | Authentication | Authorization | Expected |
| --- | --- | --- | --- | --- |
| Allowed UI → OPTIONS preflight | Pass | No credentials needed for preflight | Grants no business permissions | Returns appropriate CORS headers |
| Disallowed origin → OPTIONS | Reject | Irrelevant | Grants no permissions | Browser must not send preflighted actual request |
| Allowed UI → protected GET, not logged in | Pass | Fail | Not checked/fails | 401 or login redirect per entry point |
| Allowed UI → protected GET, wrong authority | Pass | Pass | Fail | 403 |
| Allowed UI → protected GET, right authority | Pass | Pass | Pass | 200 |
| No Origin → protected GET, valid credentials | CORS does not apply as cross-origin browser request | Pass | Pass | 200 |
| Allowed UI → browser POST, missing CSRF | Pass | Pass | Blocked by CSRF before business logic | 403, no mutation |
| Allowed UI → browser POST, valid CSRF, wrong role | Pass | Pass | Fail | 403, no mutation |
| Allowed UI → browser POST, valid CSRF, right role | Pass | Pass | Pass | 2xx, exactly one mutation |
| Allowed UI → another tenant's report | Pass | Pass | Object policy DENY | No resource leakage |
| Valid origin with expired token | Pass | Fail | Grants no permissions | 401/appropriate auth error |
| Disallowed origin, `curl` omits Origin | Proves no trust | Must verify credentials | Must verify permissions | Cannot bypass authz |

**Testing only “Allowed origin → 200” is not enough.** More revealing tests are “Allowed origin yet user lacks permission → 403” and “No Origin yet valid credentials and permission → 200”, because they prove CORS **is not authorization**.

## 18. Self-check questions

**Question 1.** An API only returns `Access-Control-Allow-Origin: https://ui.example.test`. Will a `curl` command sending no Origin be blocked by browser CORS?

**Answer:** No browser is involved to enforce the same-origin policy. The server can still process the request and apply separate authentication/authorization. CORS does not block non-browser clients.

**Question 2.** OPTIONS preflight returns 200 from the UI origin. Can a user without `report:read` read reports?

**Answer:** No. Preflight only allows the browser to attempt the actual request; it creates no user/principal and grants no report-reading permission.

**Question 3.** A script from an external site sends a simple POST. The browser blocks JavaScript from reading the response; does that guarantee the POST never ran?

**Answer:** No. With a simple request, the actual request can already be sent to the server before the browser decides not to expose the response. That is one reason CSRF protection remains necessary for apps using browser auto-credentials.

**Question 4.** Why can't `Access-Control-Allow-Origin: *` be used for credentialed browser requests?

**Answer:** Fetch/CORS forbids browsers from sharing credentialed responses with a wildcard origin. When credentials are needed, the response must name a specific allowed origin along with the matching credentials header.

**Question 5.** Does `@CrossOrigin` replace `@PreAuthorize("hasAuthority('report:read')")`?

**Answer:** No. The CORS annotation controls cross-origin browser behavior; the authorization rule determines whether the principal holds sufficient authority under server policy.

**Question 6.** Why does Spring Security need to handle CORS before authentication for preflight?

**Answer:** Preflight does not send session cookies by standard. If authentication runs first, OPTIONS can be rejected as anonymous; CORS integration lets preflight responses be returned without opening actual request permissions.

**Question 7.** A frontend stores a JWT in a cookie; can CSRF be skipped because CORS is configured accurately?

**Answer:** Not automatically. Cookies can be auto-sent by the browser; CORS does not replace CSRF and does not ensure cross-site requests were never processed by the server.

**Question 8.** A user has `report:read` and comes from an allowed UI, yet the report belongs to another tenant; how must this be handled?

**Answer:** CORS and general authority are not enough. The backend must enforce object-level/tenant authorization and deny access to out-of-scope resources.

## 19. Pre-production CORS deployment checklist

- [ ] Maintain a list of frontend origins that genuinely need cross-origin browser access; avoid arbitrary wildcards.
- [ ] Correct scheme/host/port per environment; do not confuse origin with hostname or site.
- [ ] Enable `allowCredentials` only when genuinely needed; never combine `allowedOrigins("*")` with credentialed responses.
- [ ] Handle preflight properly before authentication in Spring Security or the gateway; keep actual requests verified.
- [ ] Authentication uses verifiable credentials independent of `Origin`.
- [ ] Authorization checks actions, authorities/scopes, user, owner/tenant, and business policies on the server.
- [ ] CSRF and cookies/SameSite align with stateful apps; never treat CORS as a CSRF defense.
- [ ] CORS configs across gateway/MVC/Security do not conflict or duplicate incorrectly.
- [ ] Private responses have proper cache controls; `Vary` is verified when origin-dependent.
- [ ] Valid/invalid origins, methods, preflight, headers, and credentialed requests have all been tested.
- [ ] Tested that clients omitting Origin **cannot bypass authentication/authorization**.
- [ ] Tested that an authorized user from an allowed origin is denied when lacking permission on a specific resource.
- [ ] Tested POST with missing/wrong/valid CSRF and confirmed **no mutation** on rejected branches.
- [ ] Monitoring exists for CORS errors, actual 401/403s, and policy drift after proxy/deploys.

## 20. Conclusion and official references

**CORS governs how web browsers share responses across origins; it is not a security policy deciding who may use an API.** A valid origin creates neither a principal nor business permissions. Requests from `curl` or backend services are not bound by browser same-origin policy, so APIs must always verify credentials, authorities, object ownership, tenants, and business invariants on the server.

Use CORS allowlists to minimize cross-origin data exposure in browsers while preserving the boundaries **authentication → authorization → domain policy → CSRF (when using browser auto-credentials)**. When a browser reports a CORS error, fix the true cause in headers/preflight/proxy rather than opening all endpoints or disabling Spring Security.

References:

- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy)
- [MDN — Using Fetch / Credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
