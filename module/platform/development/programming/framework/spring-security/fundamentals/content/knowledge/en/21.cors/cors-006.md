# Processing Order of CORS and Authentication Requirements

## 1. Objectives

This lesson belongs to the **CORS** group of **Spring Security - fundamentals**. A typical scenario is a frontend at `http://localhost:5173` calling an API at `http://localhost:8080`, where the browser sends an `OPTIONS` request and then reports a CORS error while the same API works through `curl`. The common cause is that **preflight is blocked by authentication/authorization before CORS is processed**, or the origin, method, or headers are not yet permitted.

After this lesson, you will be able to:

- Explain CORS and the principle of processing **preflight before the Authentication step**.
- Distinguish `OPTIONS` preflight from **actual GET/POST**; identify the headers `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
- Distinguish **CORS, Authentication, Authorization, and CSRF**; a 200 preflight does not grant access to resources.
- Configure `http.cors(withDefaults())` with `UrlBasedCorsConfigurationSource` in Spring Security Servlet.
- Understand `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Max-Age`, and `Vary`.
- Test 200/401/403, allowed/rejected origins, POST preflight, and CSRF checks using `MockMvc`.
- Diagnose configurations involving `@CrossOrigin`, `OPTIONS permitAll`, multiple `SecurityFilterChain` beans, reverse proxies, cookies, and browser credentials mode.

**Scope:** Spring Security 6.x Servlet/MVC uses `HttpSecurity` and `SecurityFilterChain`. Spring WebFlux uses `ServerHttpSecurity`/`CorsWebFilter`; do not apply Servlet code verbatim.

## 2. CORS is browser permission to use a response, not permission to enter an API

| Mechanism | Main question | Example |
| --- | --- | --- |
| **CORS** | Is the browser origin allowed to send/read a cross-origin response with the requested method and headers? | Frontend `http://localhost:5173` calls `GET /api/me` with `Authorization` |
| **Authentication** | Does the **actual** request prove a valid identity? | HTTP Basic, session cookie, or Bearer token |
| **Authorization** | Does the authenticated identity have permission for the specific endpoint or resource? | `ROLE_ADMIN` for `GET /api/admin` |
| **CSRF** | Does an unsafe request have proper anti-forgery proof in a model where the browser auto-sends credentials? | `POST /api/ping` with CSRF token |

CORS **does not** validate passwords, JWTs, sessions, roles, scopes, or ownership. When the browser receives a 200 preflight, it only knows it **may proceed with the actual request**; the API can still return 401 or 403. Conversely, a client with the right password does not bypass CORS for a disallowed origin.

**Origin = scheme + host + port.** `http://localhost:5173` and `http://localhost:8080` are cross-origin because their ports differ. `https://app.example.com` and `http://app.example.com` have different schemes. The path `/dashboard` is not part of the origin. **Cross-origin differs from cross-site**: `SameSite` cookies use the site concept, which does not coincide completely with origin.

**CORS is not a firewall.** A server-to-server program, Postman, or `curl` can send HTTP requests without being bound by browser CORS restrictions. The backend must protect every resource with Authentication and Authorization independently of the `Origin` header.

## 3. Identifying preflight

Example of a frontend attempting to call an API with an `Authorization` header:

```javascript
fetch("http://localhost:8080/api/me", {
  method: "GET",
  headers: {
    "Authorization": "Bearer TOKEN_FROM_REAL_LOGIN_FLOW"
  }
});
```

This is a **frontend fragment** to explain CORS, not a complete token-issuing app. Never hard-code real access tokens or passwords in JavaScript. The `Authorization` header is not in the CORS-safelisted request headers group, so the browser usually has to preflight.

**OPTIONS preflight request**:

```http
OPTIONS /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflight **normally carries neither `JSESSIONID` nor the HTTP `Authorization` credentials of the actual request**. `Access-Control-Request-Headers: authorization` only states the **name** of the proposed header; it **contains no token value**. Preflight does not invoke a controller to read a profile, modifies no data, and has no Alice/Bob identity to authorize.

Not every `OPTIONS` is a preflight; a normal CORS preflight requires `Origin` and `Access-Control-Request-Method`. Do not treat arbitrary OPTIONS requests as automatically permitted without processing.

**A valid response has the form:**

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Header values and ordering vary by CORS config/framework; this is an illustrative sample, not fixed bytes.

- `Access-Control-Allow-Origin`: origin permitted to receive the response under browser policy.
- `Access-Control-Allow-Methods`: methods allowed under CORS.
- `Access-Control-Allow-Headers`: allowed request headers.
- `Access-Control-Allow-Credentials`: coordinates with credentials mode when the frontend needs cookies/auth credentials; if true, the origin must be explicit, not `*`.
- `Access-Control-Max-Age`: duration the browser may cache **preflight**, not session timeout or token expiration.
- `Vary`: helps caches distinguish origin and requested method/headers.

**After preflight:** the browser sends the actual GET/POST, now carrying the `Authorization` header or session cookie (per browser/credential policy), and the backend authenticates and authorizes it. If origin/method/header are invalid, the CORS processor may return **403**, halting the next step.

## 4. Wrong order and right order

### Wrong: auth runs before CORS

```text
Browser OPTIONS /api/me
  Origin: http://localhost:5173
  Access-Control-Request-Method: GET
  Access-Control-Request-Headers: authorization
                │
                ▼
Authentication / authorization requires authenticated()
                │
         No cookie or Authorization credentials
                │
                ▼
          401 Unauthorized / 302 /login
                │
                ▼
Browser reports preflight/CORS error
Actual GET may never have been sent
```

This is an **ordering** issue, not evidence that the API GET must be public. Adding credentials to OPTIONS is not the answer: browsers do not use preflight to send the actual request's token.

### Right: CORS before filters requiring Authentication

```text
Servlet request
      │
      ▼
FilterChainProxy selects SecurityFilterChain matching path
      │
      ▼
CorsFilter integrated by http.cors(...)
      │
      ├─ Valid preflight → 200 + CORS allow headers, stop
      ├─ Policy-violating preflight → 403, stop
      └─ Origin-valid actual request → continue
                   │
                   ▼
               CsrfFilter
                   │
                   ▼
          Authentication filters
                   │
                   ▼
           AuthorizationFilter
                   │
                   ▼
               Controller
```

The diagram is a simplified model. In Spring Security Servlet, **`CorsFilter` is integrated at an appropriate position before security filters requiring credentials**; the full order contains many more filters. Thus, “CORS must be processed before Spring Security” in documentation means **before the steps requiring Authentication/Authorization**. `CorsFilter` can still sit **inside** `SecurityFilterChain` when configured via `http.cors(...)`, and does not have to be a global filter sitting outside all of Spring Security.

Do not expect swapping the order of `.cors(...)` and `.authorizeHttpRequests(...)` in Java source code to change filter ordering on its own; Spring Security manages filter ordering internally.

**The right order preserves safety:** a 200 preflight grants **no** permissions; the actual request still needs Authn/Authz and can be blocked by CSRF if it uses an unsafe method.

## 5. Why is `permitAll OPTIONS` alone not enough?

This configuration is often used as a quick fix:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
    .anyRequest().authenticated()
)
```

This is a **fragment**, **not a complete CORS configuration**. `permitAll()` only opens one **authorization** step, yet generates no `Access-Control-Allow-Origin/Methods/Headers`, enforces no trusted origin list, and does not guarantee a preceding custom authentication filter will not block OPTIONS.

`web.ignoring().requestMatchers(HttpMethod.OPTIONS, "/**")` also does not generate CORS responses on its own and may bypass security filters unnecessarily. Best practice is **letting the CORS processor recognize/resolve preflight**, while actual methods remain subject to security policies.

## 6. Spring Security Servlet configuration

Create a `UrlBasedCorsConfigurationSource` with a narrow allowlist:

```java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("http://localhost:5173"));
    config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-CSRF-TOKEN")
    );
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

This is a fragment; the runnable code in section 8 has full imports/classes. Enable CORS in `HttpSecurity`:

```java
http.cors(withDefaults());
```

Spring Security can use the `UrlBasedCorsConfigurationSource` bean to configure CORS handling before authentication. When Spring MVC is on the classpath without a separate `CorsConfigurationSource`, Spring Security can fall back to Spring MVC's CORS config. `@CrossOrigin` on a controller **cannot resolve** preflight if a security filter already blocked the request before MVC received it.

Parameters to check:

| Setting | Effect | Warning |
| --- | --- | --- |
| `allowedOrigins` | Origin allowlist, including scheme/host/port | Never use wildcard with credentials true |
| `allowedMethods` | Methods browser is permitted to call | Do not open DELETE/PUT unless needed |
| `allowedHeaders` | Request headers browser is permitted to send | Include `Authorization` for bearer/Basic, `Content-Type` for JSON |
| `allowCredentials` | Whether response supports credentialed cross-origin mode | Does not replace login; true requires exact origins |
| `maxAge` | Preflight cache duration | Not session/token expiry |
| `registerCorsConfiguration` | Path mapping for CORS | `/api/**` does not cover/grant CORS for `/login` |

### Cookies and CORS credentials

If frontend `https://app.example.com` uses a session cookie from backend `https://api.example.com`, the actual request can send the cookie per `credentials:"include"` and cookie policy. CORS preflight still must never be forced to prove identity.

**Configuration fragment for a cookie-based frontend:**

```java
CorsConfiguration cfg = new CorsConfiguration();
cfg.setAllowedOrigins(List.of("https://app.example.com"));
cfg.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cfg.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
cfg.setAllowCredentials(true);
```

**Frontend fragment:**

```javascript
fetch("https://api.example.com/account", {
  credentials: "include",
  method: "GET"
});
```

With credentials mode `include`, the browser needs `Access-Control-Allow-Credentials: true` and a specific permitted `Access-Control-Allow-Origin` for the frontend to read the response. `Access-Control-Allow-Origin: *` **is invalid** for credentialed responses; Spring Framework forbids `allowedOrigins("*")` combined with `allowCredentials(true)`. Cookies also depend on `Secure`, `SameSite`, Domain/Path, and browser policies. Cross-origin is not necessarily cross-site; do not set `SameSite=None` indiscriminately.

**CORS does not replace CSRF.** The browser can auto-send a session cookie on an unwanted request. For POST/PUT/PATCH/DELETE in session/cookie apps, CSRF protection or an equivalent measure is required, even when CORS allows the origin.

## 7. Distinguishing 200, 401, and 403

| Scenario | Typical response in lab | Cause category |
| --- | --- | --- |
| Valid preflight, no credentials | **200** | CORS accepts origin/method/headers |
| Preflight from disallowed origin | **403** | CORS |
| Preflight requesting unlisted method/header | **403** | CORS |
| Actual GET valid origin, missing credentials | **401** | HTTP Basic authentication |
| Actual GET valid origin, wrong password | **401** | Authentication |
| Actual GET authorized user | **200** | Passed authn/authz |
| Actual GET user lacks `ROLE_ADMIN` | **403** | Authorization |
| Actual POST valid origin, valid credentials, missing CSRF | **403** | `CsrfFilter` |
| Actual GET disallowed origin even with valid Basic | **403** | Actual request CORS |
| Request without `Origin`, valid Basic | Possibly **200** | No browser CORS applied, still must authenticate |

HTTP Basic usually returns 401 with `WWW-Authenticate`. If an app uses form login instead of Basic, an unauthenticated request may receive 302 to `/login`. **403 does not always mean wrong role**: it can come from the CORS processor or `CsrfFilter`. To diagnose, inspect method, Origin, preflight headers, and where the response was produced.

## 8. Runnable Java 17 demo, Spring Boot 3.5.12

We build a backend with two local users:

- `alice / alice123` with `ROLE_USER`.
- `admin / admin123` with `ROLE_ADMIN`.

API routes:

| Path | Method | Access |
| --- | --- | --- |
| `/public` | GET | Public, not used for cross-origin testing |
| `/api/me` | GET | Valid authentication |
| `/api/admin` | GET | `ROLE_ADMIN` |
| `/api/ping` | POST | Authentication and CSRF token; POST is illustrative only, stores no data |

The lab uses **HTTP Basic on localhost only** and issues no JWTs. Frontend `http://localhost:5173` is only an allowlisted origin for testing. Production must use HTTPS, identity management, and secure session/token flows; **never send passwords in frontend JavaScript**.

### 8.1. Files

```text
cors-auth-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/corsauth/
    │   ├── CorsAuthApplication.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/com/example/corsauth/
        └── CorsAuthTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'cors-auth-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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
```

Requires JDK 17+ and a compatible Gradle 8.4+. Because the app depends on Spring libraries, use Gradle/Wrapper to build the classpath; it cannot run with bare `javac`/`java` without dependencies.

### 8.2. Main

**`src/main/java/com/example/corsauth/CorsAuthApplication.java`**

```java
package com.example.corsauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsAuthApplication.class, args);
    }
}
```

### 8.3. CORS + Authentication + Authorization

**`src/main/java/com/example/corsauth/SecurityConfiguration.java`**

```java
package com.example.corsauth;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cfg = new CorsConfiguration();
        cfg.setAllowedOrigins(List.of("http://localhost:5173"));
        cfg.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cfg.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cfg.setAllowCredentials(false);
        cfg.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cfg);
        return source;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .cors(withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .csrf(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
```

**Reading the configuration by function:**

1. `UrlBasedCorsConfigurationSource` holds the CORS policy for `/api/**` with one specific frontend origin; it disallows `https://evil.example`.
2. `.cors(withDefaults())` integrates preflight handling before the step requiring HTTP Basic authentication.
3. `Authorization` is in allowed request headers, yet **no credentials are sent in preflight**.
4. `.requestMatchers("/api/admin").hasRole("ADMIN")` comes before the broader `/api/**.authenticated()` rule, preventing the broader rule from shadowing the role rule.
5. `.httpBasic(withDefaults())` authenticates the actual request; `formLogin(...disable())` avoids HTML login redirects in the API demo.
6. `.csrf(withDefaults())` preserves CSRF checking. For `POST /api/ping`, `CsrfFilter` still demands a token; a 200 preflight does not bypass CSRF.
7. `setAllowCredentials(false)` is for a lab not using cross-origin login cookies. To support browser `credentials:"include"` with sessions, the policy must be redesigned.
8. BCrypt hashes passwords in the demo user store; passwords in this document are strictly for local learning.

### 8.4. Controller

**`src/main/java/com/example/corsauth/DemoController.java`**

```java
package com.example.corsauth;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("user", auth.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin(Authentication auth) {
        return Map.of("admin", auth.getName());
    }

    @PostMapping("/api/ping")
    public Map<String, String> ping(Authentication auth) {
        return Map.of("status", "POST accepted", "user", auth.getName());
    }
}
```

The `/api/ping` route only produces a lab response and persists no real data. It serves as a POST example to observe CSRF. Real apps need resource-level authorization, transactions, and input validation.

### 8.5. Running

```bash
gradle test
gradle bootRun
```

With a matching Gradle Wrapper version, use `./gradlew test`/`./gradlew bootRun` on Linux/macOS or `gradlew.bat test`/`gradlew.bat bootRun` on Windows. The app runs at `http://localhost:8080` if the port is free and unconfigured otherwise.

### 8.6. Curl: comparing preflight and actual requests

**Valid preflight, no Basic credentials:**

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Expect **200** and `Access-Control-Allow-Origin: http://localhost:5173` with matching allowed methods/headers. Do not pass `-u` on preflight.

**Preflight with wrong origin:**

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: https://evil.example' \
  -H 'Access-Control-Request-Method: GET'
```

Expect **403** from CORS.

**Preflight requesting disallowed DELETE:**

```bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE'
```

Expect **403**.

**Actual GET with allowed origin but missing credentials:**

```bash
curl -i 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:5173'
```

Expect **401 Unauthorized** from HTTP Basic. When Spring Security integrates CORS properly, the allowed browser origin can see CORS headers on the 401 response.

**Actual GET with valid credentials:**

```bash
curl -i -u alice:alice123 \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/me'
```

Expect **200** with JSON containing `"user":"alice"`.

**Actual GET with wrong role:**

```bash
curl -i -u alice:alice123 \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/admin'
```

Expect **403** from `hasRole("ADMIN")`. With `-u admin:admin123`, `/api/admin` returns **200** and `"admin":"admin"`.

**CORS rejects origin even with valid credentials:**

```bash
curl -i -u alice:alice123 \
  -H 'Origin: https://evil.example' \
  'http://localhost:8080/api/me'
```

Expect **403** from CORS. If `Origin` is omitted while valid Basic credentials are present, `curl` can receive **200**; CORS is not a server firewall.

**POST with valid Basic but missing CSRF token:**

```bash
curl -i -X POST -u alice:alice123 \
  -H 'Origin: http://localhost:5173' \
  'http://localhost:8080/api/ping'
```

Expect **403** from `CsrfFilter`. Even if the preceding POST preflight returned 200, this remains right: **CORS and CSRF are two independent decisions**.

`curl` does not run browser preflight caching or CORS blocking; it simply shows you the HTTP response from the server. Real browser testing is still necessary to verify whether the frontend can read responses.

### 8.7. MockMvc tests: preflight, Authentication, Authorization, CSRF

**`src/test/java/com/example/corsauth/CorsAuthTests.java`**

```java
package com.example.corsauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAuthTests {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightNeedsNoCredentials() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", FRONTEND))
            .andExpect(header().exists("Access-Control-Allow-Methods"))
            .andExpect(header().exists("Access-Control-Allow-Headers"))
            .andExpect(header().doesNotExist("WWW-Authenticate"));
    }

    @Test
    void preflightForPostDoesNotNeedCredentials() throws Exception {
        mvc.perform(options("/api/ping")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "authorization, content-type"))
            .andExpect(status().isOk());
    }

    @Test
    void preflightRejectsUnknownOrigin() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "GET"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }

    @Test
    void preflightRejectsUnlistedMethod() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void preflightRejectsUnlistedHeader() throws Exception {
        mvc.perform(options("/api/me")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "X-Secret-Internal"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualWithoutAuthenticationIs401() throws Exception {
        mvc.perform(get("/api/me").header("Origin", FRONTEND))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", FRONTEND));
    }

    @Test
    void actualWithWrongPasswordIs401() throws Exception {
        mvc.perform(get("/api/me")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void actualWithCorrectAuthenticationIs200() throws Exception {
        mvc.perform(get("/api/me")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void allowedOriginDoesNotGiveAdminRole() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                .header("Origin", FRONTEND)
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.admin").value("admin"));
    }

    @Test
    void actualWithForbiddenOriginIs403() throws Exception {
        mvc.perform(get("/api/me")
                .header("Origin", "https://evil.example")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void noOriginDoesNotRemoveAuthenticationRequirement()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preflightSuccessDoesNotBypassCsrf() throws Exception {
        mvc.perform(options("/api/ping")
                .header("Origin", FRONTEND)
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isOk());

        mvc.perform(post("/api/ping")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/ping")
                .header("Origin", FRONTEND)
                .with(httpBasic("alice", "alice123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("POST accepted"));
    }
}
```

`httpBasic()` from Spring Security Test builds HTTP Basic credentials for the actual request; `csrf()` adds a valid CSRF token **in tests**, not a fixed value for browsers.

The tests demonstrate:
- Preflight **200 without credentials**.
- Valid origin yet missing/wrong credentials → actual **401**.
- Valid user yet missing role → actual **403**.
- Disallowed origin → CORS **403**.
- POST preflight **200**, yet actual POST without CSRF **403**; with valid auth and CSRF **200**.
- Omitting Origin does not cause the backend to skip Authentication.

**Limitations:** `MockMvc` does not verify cookie behavior, browser CORS preflight caching, reverse proxies, TLS, or CDNs. Those require testing in a real browser and deployment-like environment. The code examples were statically reviewed; `gradle test` results are expected goals and are not claimed to have been executed in this lesson.

## 9. Multiple SecurityFilterChain beans: select chain first, CORS before auth within chain

There are **two orderings** to verify:

1. `FilterChainProxy` selects the **first matching SecurityFilterChain** based on `@Order` and `securityMatcher`.
2. Within the selected chain, `CorsFilter` must process preflight **before** filters requiring authentication.

A broad chain ordered ahead of `/api/**` can shadow the API chain, causing the CORS source intended for the API not to be used. `OPTIONS /api/orders` shares the path `/api/orders`, so a chain matcher restricted to GET without OPTIONS can also fail.

**Multiple-chain fragment:**

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .cors(cors -> cors.configurationSource(apiCorsSource))
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(withDefaults())
        .build();
}
```

This **is not a standalone runnable file**: it needs imports, an `apiCorsSource` bean, and a fallback chain for remaining routes. If there are **multiple `CorsConfigurationSource` beans**, Spring Security may not know which one to pick automatically; in that case pass the source explicitly per chain via `configurationSource(...)`.

`securityMatcher` selects the chain, whereas `requestMatchers` inside the chain selects authorization rules; they are not interchangeable tools.

## 10. Troubleshooting in browser and proxy

A real system may have:

```text
Browser → CDN/ingress → API gateway → Servlet filters → Spring Security → MVC
```

If the gateway demands login before forwarding OPTIONS to Spring Boot, changing `http.cors(...)` on the backend will not fix it.

**Investigation sequence:**

1. Open **DevTools → Network** and inspect OPTIONS and the actual request separately.
2. On OPTIONS, check `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, status, and `Access-Control-Allow-Origin/Methods/Headers`.
3. OPTIONS **401/302**: likely blocked by authentication/login entry point before CORS at the gateway or filter chain.
4. OPTIONS **403**: check origin/method/request header allowlists; do not assume it is a role issue.
5. OPTIONS **200**, GET **401**: CORS succeeded; check credentials on the actual request.
6. OPTIONS **200**, GET/POST **403**: inspect role/scope/CSRF/actual CORS; identify which filter produced the error.
7. Server actual response **200** yet JS still reports CORS: check ACAO/ACAC headers on the **actual response**, duplicate ACAO, wildcards, redirects, caching, and credentials mode.
8. Only certain URLs fail: check CORS mapping `/api/**`, multiple chains, MVC `@CrossOrigin`, proxy path rewrites.
9. Fails only after deploy: check actual frontend scheme/host/port, TLS redirects, gateway auth on OPTIONS, and `Vary` on caches.
10. Never write real Authorization headers, access tokens, session cookies, or passwords into logs/bug reports.

| Observation | Primary likelihood |
| --- | --- |
| OPTIONS 401 + WWW-Authenticate | Authentication before CORS |
| OPTIONS 302 to /login | Form login handling preflight |
| OPTIONS 403 | Origin/method/header rejected by CORS |
| OPTIONS 200, actual GET 401 | Actual request authentication failure |
| OPTIONS 200, actual GET 403 missing role | Authorization |
| OPTIONS 200, actual POST 403 missing CSRF | `CsrfFilter` |
| `curl` 200, browser does not send GET | Browser preflight failed |
| Response 200 yet JS cannot read it | Actual CORS headers/credentials policy incorrect |
| Fails only behind proxy | Gateway/ingress/cache/path rewrite |

## 11. Common pitfalls

| Wrong | Right |
| --- | --- |
| “OPTIONS must log in like GET” | Preflight is handled by CORS **independently of Authentication** |
| “OPTIONS permitAll is enough” | Need CORS processor to return exact allow headers |
| “200 preflight means the API is open” | Actual request still runs authn/authz/CSRF |
| “`Access-Control-Request-Headers: authorization` is the token” | It only lists the header **name** |
| “CORS blocks all clients without an origin” | CORS is primarily a **browser policy**; backend still needs auth |
| “CORS error? Disable CSRF” | CORS and CSRF are different |
| “`@CrossOrigin` definitely handles OPTIONS” | Security/gateway may block before MVC |
| “`allowedOrigins("*")` with credentials=true is fine” | No, specific origins are required |
| “Cross-origin always means cross-site” | Two different concepts |
| “Spring Security only has one chain” | Multiple chains are possible; check `@Order`/`securityMatcher` |
| “Postman works so CORS is right” | Postman does not block by browser CORS |
| “403 always means missing ROLE_ADMIN” | CORS/CSRF can also return 403 |

### Pre-release production check

Confirm origin allowlists per environment, verify CORS policies cover the right paths/chains, ensure preflight is not authenticated at the gateway, keep actual requests protected by role/scope/object authorization, include proper headers on 401/403 responses for trusted origins, test cookies/CSRF in a real browser, ensure CDN caches respect `Vary`, and keep logs free of credentials.

## 12. Self-check questions

**1.** Why does preflight normally lack `JSESSIONID` or the actual request's `Authorization`? — Because preflight only asks whether origin/method/headers are permitted; the browser does not send it as an authenticated request.

**2.** Does OPTIONS 200 prove Alice can access `/api/admin`? — No. Actual GET can still return 403 if ROLE_ADMIN is missing.

**3.** Are `http://localhost:5173` and `http://localhost:8080` same-origin? — No, different ports.

**4.** Why is `OPTIONS /** permitAll` not enough? — It does not emit `Access-Control-Allow-*` or enforce CORS policy.

**5.** Does `Access-Control-Request-Headers: authorization` contain the bearer token? — No, only the header name.

**6.** What do OPTIONS 200, GET 401 mean? — The browser was allowed to proceed, yet the actual request had missing/invalid credentials.

**7.** What could OPTIONS 200, POST 403 be? — CSRF, authorization, or actual CORS depending on the request; check which filter caused the error.

**8.** Why can curl GET return 200 even when CORS is wrong? — Curl does not enforce browser CORS restrictions; Authn/Authz still protect the server.

**9.** Can ACAO `*` be used with `Access-Control-Allow-Credentials: true`? — No; use specific permitted origins.

**10.** What two orderings must be checked with multiple chains? — `@Order`/`securityMatcher` selecting the chain, and CorsFilter before steps requiring Authentication within that chain.

**11.** Does a `SameSite=None; Secure` cookie automatically allow cross-origin responses? — No. Cookie policy and CORS response policy are separate.

**12.** Does a valid access token replace a CORS allowlist? — No; the token authenticates the actual request, whereas CORS decides whether the browser exposes cross-origin responses.

**13.** Does CORS replace CSRF tokens for cookie-based POSTs? — No. CORS and CSRF protect against different threats.

**14.** If an API returns 401 on preflight in Spring Security, what should you check first? — CORS integration with the chain/gateway and filter order, because preflight carries no credentials.

**15.** Does `Access-Control-Max-Age: 600` mean the token lives for 600 seconds? — No; it is the preflight cache duration.

## 13. Key takeaways

- **CORS must be processed before authentication** for preflight.
- **Preflight does not authenticate users**, nor does it carry `Authorization` or login cookies of the actual request.
- In Spring Security Servlet, enable `http.cors(withDefaults())` and configure a `UrlBasedCorsConfigurationSource` or properly integrated MVC source.
- **A 200 preflight does not open endpoints**: actual requests can still return 401/403/200.
- `OPTIONS permitAll` and disabling CSRF are not substitutes for CORS.
- **CORS is not authorization or a firewall**; curl/non-browser callers must still be guarded by authn/authz.
- Credentials true requires a specific origin allowlist, never `*`; browser cookies carry separate SameSite/Secure/CSRF constraints.
- With multiple chains/proxies, verify **chain selection order**, **CorsFilter**, and where responses originate.
- Debug **OPTIONS and actual requests** separately rather than relying on a single “CORS error” console line.

### References

- Spring Security 6.5 — CORS: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html
- Spring Security — Java Configuration / Multiple Chains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Framework — Spring MVC CORS: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — MockMvc testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- MDN — CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Request.credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
