# Ordering CORS Before Authentication and Authorization in Spring Security WebFlux

## Learning Objectives

After this lesson, you will be able to:

1. Explain why browsers send a **CORS preflight** via HTTP `OPTIONS` **before the actual request**, and why preflight does not carry the actual request's session cookie or `Authorization` header.
2. Distinguish **CORS**, **authentication**, **authorization**, and **CSRF**: these are separate mechanisms and do not substitute for one another.
3. Describe the proper order in Spring Security WebFlux: CORS is evaluated early, a valid preflight terminates at the CORS step, and the actual request proceeds through authentication and authorization.
4. Use `ServerHttpSecurity.cors(...)` with `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`, configuring origins, methods, headers, and credentials minimally.
5. Distinguish when to use `CorsWebFilter`, `CorsConfigurationSource`, `WebFluxConfigurer.addCorsMappings(...)`, and `@CrossOrigin`, avoiding double CORS registration or incorrect filter ordering.
6. Build a Java 17+ / Spring Boot 3.x application and test with `WebTestClient`: unauthenticated OPTIONS succeeds, unauthenticated actual GET returns 401, authenticated user lacking role returns 403, and disallowed origin gets CORS rejection.
7. Analyze multi-chain setups, gateways/proxies, `Access-Control-Allow-Credentials`, `Vary`, SameSite cookies, CORS errors mistaken for authorization errors, and CSRF protection on unsafe methods.

> Scope: **Spring Security reactive/WebFlux**, Spring Security 6.5.x and Spring Framework 6.2.x on Spring Boot 3.5.x, Java 17+. Names like `CorsFilter` (Servlet), `HttpSecurity`, `SecurityFilterChain`, and `HttpServletRequest` belong to the MVC/Servlet stack and are not used in this WebFlux lesson. In WebFlux you need `CorsWebFilter`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerWebExchange`.

## 1. What Does Processing CORS Before Authentication Mean?

Suppose a UI at `http://localhost:3000` needs to call a protected API at `http://localhost:8080/api/private`. These two addresses have different **origins** because their ports differ, even though both use `localhost`.

A JavaScript call using an `Authorization` header (which is not a safelisted header) will typically cause the browser to send two HTTP requests:

1. **Preflight**: `OPTIONS /api/private` with `Origin`, `Access-Control-Request-Method: GET`, and `Access-Control-Request-Headers: authorization`. The browser asks the server: "May this origin use that method and header?"
2. **Actual request**: only when preflight is approved does the browser execute `GET /api/private` with the appropriate credentials, and then check the actual request's CORS response.

**Preflight is not a user login attempt.** Under the CORS protocol, preflight requests must not send credentials such as cookies or HTTP authentication. If Spring Security enforces `authenticated()` on the preflight **before CORS has a chance to recognize it**, the server can return 401 or redirect to login; the browser treats the CORS check as failed and **never sends the actual GET**.

Therefore:

- **CORS before authentication**: allows valid preflights to be evaluated by origin/method/header without requiring a logged-in user.
- **Authentication after CORS**: only the actual request validates cookies, HTTP Basic, Bearer tokens, or other authentication mechanisms.
- **Authorization after authentication**: the actual request must have sufficient permissions for the resource.
- **CSRF**: must still protect unsafe requests where the browser automatically attaches credentials, regardless of whether CORS allowed the origin.

Important: processing CORS first **does not mean every OPTIONS request is allowed or endpoints become public**. Preflights carrying `Origin` and `Access-Control-Request-Method` are evaluated by the CORS policy; ordinary OPTIONS requests lacking those markers are not automatically granted bypass past authorization.

### Comparison Table

| Step | Purpose | What does it inspect? | Does it prove the user is authorized? |
| --- | --- | --- | --- |
| CORS | May the browser call/read the cross-origin response per policy? | Origin, request method, request headers, credentialed mode | **No** |
| Authentication | Who is calling the API? | Session, Basic, Bearer, mTLS, or identity source | Establishes identity only |
| Authorization | What is that principal allowed to do? | Role, permission, owner, tenant, resource state | **Yes**, per rules |
| CSRF | Does a state-changing request carry a valid token/source? | CSRF token/repository and anti-forgery checks | Does not replace authorization |

## 2. Preflight Is an Independent Request, Not an "Authenticated" OPTIONS

An example of a valid preflight looks like:

```http
OPTIONS /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

There is no session cookie and no `Authorization: Basic ...` in this request. The browser does not try to log in via preflight. If policy permits, the server may respond:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

These are **illustrative response headers**; casing, header ordering, 200 vs. 204 status, and whether multiple `Vary` values are combined depend on the implementation. The browser checks the requested **origin**, method, and header; if the response is invalid, the actual request is blocked by the browser. The browser may cache the preflight result for a period per policy, though `maxAge=1800` does not force every browser to cache for the full 1800 seconds.

The actual request is separate:

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Authorization: Basic ...
```

This actual request must still go through Spring Security authentication and authorization. If credentials are missing, HTTP Basic typically returns `401 Unauthorized`; if authenticated but lacking a role, it typically returns `403 Forbidden`. If authorized, the response includes the data along with valid CORS headers so the browser lets the frontend read it.

**Passing CORS preflight does not issue a "free pass" skipping security for the actual request.** It only confirms the browser may proceed to the next actual HTTP step.

### When Does the Browser Send a Preflight?

Browsers typically preflight when a cross-origin request uses a method, header, or content type outside the CORS-safelisted set. Examples include `Authorization`, `X-Request-ID`, `Content-Type: application/json`, or the `PUT` method. A simple cross-origin GET without custom headers usually **does not** preflight; the browser sends the actual GET directly, though CORS must still be checked on the actual GET's response.

Preflight specifies the actual intended method in `Access-Control-Request-Method`, rather than merely asking whether `OPTIONS` itself is allowed. In the example above, the method requiring permission is **GET**.

## 3. Diagrams of Correct and Incorrect Processing Order

### Correct: CORS Filter Before Security Authentication

```text
Frontend http://localhost:3000
          |
          | OPTIONS /api/private
          | Origin: http://localhost:3000
          | Access-Control-Request-Method: GET
          v
Spring WebFlux filter chain
          |
          +--> CORS processing (CorsWebFilter / CorsSpec)
          |        |
          |        +--> Origin/method/header valid?
          |        |      |
          |        |      +--> Yes -> preflight response (200/204)
          |        |      +--> No -> CORS reject (typically 403)
          |        |
          |        +--> No user identity needed for preflight
          |
          +--> Does not enter AuthenticationWebFilter / AuthorizationWebFilter
               when preflight is handled and completes at CORS

Browser receives successful preflight
          |
          | GET /api/private + actual credentials (if any)
          v
CORS checks origin on actual request
          |
          +--> HTTP Basic/session/JWT authentication
          |
          +--> Authorization (authenticated/role/ACL)
          |
          +--> Controller/HandlerFunction
          |
          +--> Response + Access-Control-Allow-Origin for browser
```

### Incorrect: Security Blocks Preflight Before CORS

```text
OPTIONS /api/private without cookie / Authorization
          |
          v
Authentication / authorization runs before CORS
          |
          +--> No principal -> 401 or login redirect
          |
          v
Browser: CORS preflight fails
          |
          +--> Actual GET is never sent
          +--> DevTools may report "CORS error"
```

Operational hazard: the backend may return 401, yet frontend JavaScript only sees a generic CORS error and assumes the API "disallows the origin". Inspect the **Network tab** separately for the `OPTIONS` request and the actual request, rather than looking only at the `fetch()` exception.

### Does `OPTIONS /** permitAll()` Solve This?

The following configuration is an incomplete workaround:

```java
// Anti-pattern if used as the sole CORS solution.
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
        .anyExchange().authenticated())
```

Permitting `OPTIONS` at authorization **does not automatically generate** `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers`. If CORS is not handled properly, the browser still rejects the preflight. It also permits non-CORS `OPTIONS` requests, whereas the actual goal is to handle only CORS requests matching your origin/method/header policy.

The proper policy: **wire a CORS configuration source into the early CORS layer**, keeping authorization strict for actual requests.

## 4. Ordering in WebFlux's SecurityWebFilterChain

In Spring Security 6.5, `SecurityWebFiltersOrder` defines milestones in relative order:

```text
... HTTP_HEADERS_WRITER
... HTTPS_REDIRECT
    CORS
    CSRF
    REACTOR_CONTEXT
    HTTP_BASIC / FORM_LOGIN / AUTHENTICATION
    ...
    ANONYMOUS_AUTHENTICATION
    ...
    EXCEPTION_TRANSLATION
    AUTHORIZATION
```

This list **only illustrates the relative order of key stages**; it is not an exhaustive copy of the enum or a fixed list of every filter in every configuration. A filter may be absent if its corresponding feature is disabled, and applications can intentionally insert other filters at specific positions.

Spring Security WebFlux's `ServerHttpSecurity.CorsSpec` ensures `CorsWebFilter` is placed at the proper CORS position in the security chain. In version 6.5, the API:

```java
// Configuration snippet inside the SecurityWebFilterChain bean:
http.cors(cors -> cors.configurationSource(corsConfigurationSource));
```

uses the supplied `org.springframework.web.cors.reactive.CorsConfigurationSource`. If you configure `.cors(Customizer.withDefaults())`, Spring Security looks for a `CorsConfigurationSource` bean to integrate; **without an appropriate source, do not expect CORS headers to be generated automatically**.

Note: `.cors(cors -> cors.disable())` disables **CORS integration inside Spring Security**; it does not turn off the browser's same-origin policy. Disabling it by mistake still causes cross-origin frontend requests to fail with CORS errors; never use `disable()` as a fix.

## 5. CORS APIs Frequently Confused Between WebFlux and Servlet

| Role | **WebFlux reactive** | **Servlet/MVC — not used in this lesson** |
| --- | --- | --- |
| Security DSL | `ServerHttpSecurity` | `HttpSecurity` |
| Filter chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| CORS filter | `org.springframework.web.cors.reactive.CorsWebFilter` | `org.springframework.web.filter.CorsFilter` |
| Source interface | `org.springframework.web.cors.reactive.CorsConfigurationSource` | `org.springframework.web.cors.CorsConfigurationSource` |
| URL mapping source | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.UrlBasedCorsConfigurationSource` |
| Exchange/request | `ServerWebExchange` | `HttpServletRequest` |
| Controller mapping | WebFlux HandlerMapping | MVC HandlerMapping |
| Authentication | Reactive security WebFilters | Servlet filters |

The `CorsConfiguration` class (without `reactive`) is **shared**: `org.springframework.web.cors.CorsConfiguration`. Importing the right source/filter is therefore critical when your IDE auto-suggests types.

### Three Ways to Configure CORS in WebFlux

**Approach A — Preferred in this lesson:** provide a `UrlBasedCorsConfigurationSource` and pass it directly via `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))`. Advantage: the security configuration explicitly shows which CORS source is used, and Security manages its ordering.

**Approach B — Standalone `CorsWebFilter` bean:** Spring WebFlux can use a `CorsWebFilter` bean ordered ahead of the Spring Security WebFilter using an appropriate `@Order`. Useful when using functional endpoints or wanting CORS across routes outside a security chain. If you pick this approach, **do not accidentally enable a second CORS handler inside Security** with a conflicting policy.

**Approach C — `WebFluxConfigurer.addCorsMappings(...)` / `@CrossOrigin`:** this is `HandlerMapping`-level CORS, convenient for describing URL/handler rules, yet it runs **after** security WebFilters. If security rejects a preflight earlier, controller annotations never get a chance to run. You must verify CORS integration ahead of security whenever endpoints are protected.

Each approach has its place; choose one primary place to define the policy and test the actual execution path. Never copy Servlet `CorsFilter` or `FilterRegistrationBean` tutorials and expect them to work in WebFlux.

## 6. Runnable Java 17+ Example: CORS Before HTTP Basic and Authorization

The example includes:

- Allowed dev frontend origin: **`http://localhost:3000`**.
- API: **`http://localhost:8080`**, using Spring WebFlux.
- Authentication: HTTP Basic for clear testing; demo accounts are for local machine use only. In real deployments, use HTTPS and an appropriate identity provider.
- Endpoints: `GET /api/public` needs no login, `GET /api/private` requires authentication, and `GET /api/admin` requires role `ADMIN`.
- CORS configured for `/api/**`, accepting only the specified dev origin, method `GET`, and headers `Authorization`, `Content-Type`.
- `Access-Control-Allow-Credentials: true` to demonstrate credentialed browser requests; in production, enable only when cookies/HTTP auth genuinely require it and always pair with an explicit origin allowlist.

### 6.1. Project Structure

```text
cors-order-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/corsorder/
        CorsOrderApplication.java
        SecurityConfiguration.java
        ApiController.java
      resources/
        application.yml
    test/
      java/example/corsorder/
        CorsOrderIntegrationTest.java
```

Do not add `spring-boot-starter-web`; if Spring MVC and WebFlux are both on the classpath, Spring Boot normally prefers a Servlet application.

### 6.2. Complete Gradle Setup

**`settings.gradle`**:

```groovy
rootProject.name = 'cors-order-demo'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Both plugin versions above are released versions forming a Spring Boot 3.5 / Spring Security 6.5 baseline example. To run, you need a compatible Gradle Wrapper (or installed Gradle). In real projects, use supported patch versions and apply security updates rather than pinning older releases if operations policies require upgrades.

**`src/main/resources/application.yml`**:

```yaml
server:
  port: 8080

spring:
  application:
    name: cors-order-demo
```

### 6.3. Main Class

**`src/main/java/example/corsorder/CorsOrderApplication.java`**:

```java
package example.corsorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsOrderApplication.class, args);
    }
}
```

### 6.4. CORS and Spring Security WebFlux Configuration

**`src/main/java/example/corsorder/SecurityConfiguration.java`**:

```java
package example.corsorder;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of("http://localhost:3000"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type"));
        config.setAllowCredentials(true);
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("local-test-password"))
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("local-test-password"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {
        return http
                .cors(cors -> cors.configurationSource(
                        corsConfigurationSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/private")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Why is this ordered properly?**

1. `UrlBasedCorsConfigurationSource` belongs to `org.springframework.web.cors.reactive`. A URL like `/api/private` matches `/api/**`.
2. `config.setAllowedOrigins(...)` matches the **exact origin** including scheme/host/port. `http://localhost:3000` differs from `http://127.0.0.1:3000` and `https://localhost:3000`.
3. `setAllowedMethods(List.of("GET"))` permits the **actual method GET**. Browser preflight uses HTTP OPTIONS with `Access-Control-Request-Method: GET`, so you do not need to add OPTIONS to allowed methods just for a GET preflight to succeed.
4. `setAllowedHeaders(List.of("Authorization","Content-Type"))` accepts the headers requested for the actual call. If the frontend needs `X-Correlation-ID`, add it to the allowlist as required.
5. `setAllowCredentials(true)` enables credentialed CORS only for the allowlisted origin; never combine `allowCredentials(true)` with `allowedOrigins("*")`.
6. `setMaxAge(1800L)` lets browsers cache the preflight result up to policy limits; it is not a session or access token lifetime.
7. `http.cors(cors -> cors.configurationSource(...))` integrates CORS in the security chain **ahead of** CSRF, authentication, and authorization. The order of fluent DSL calls is not the WebFilter execution order; the framework derives filter order from `SecurityWebFiltersOrder`.
8. `anyExchange().denyAll()` remains the default; valid preflights are handled earlier by the CORS filter, while unauthenticated actual requests are still denied.
9. `httpBasic(...)` lets the demo observe the `Authorization` header; `formLogin(...)` is disabled so API clients are not redirected to HTML login. CSRF stays at default; the demo only exposes GET so business endpoints do not require a CSRF token.
10. `PasswordEncoder` hashes the demo users' passwords. Never use `{noop}` or hardcoded local accounts in production.

**Important:** the source bean is not a standalone `CorsWebFilter`. Here we let **Spring Security create/integrate `CorsWebFilter`**, avoiding duplicate handling in two places. This configures a **single** `SecurityWebFilterChain` for all requests.

### 6.5. Controller to Prove Preflight Never Enters Business Code

**`src/main/java/example/corsorder/ApiController.java`**:

```java
package example.corsorder;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final AtomicInteger privateReads = new AtomicInteger();

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    public Mono<String> privateInfo() {
        return Mono.fromSupplier(() -> {
            privateReads.incrementAndGet();
            return "private-data";
        });
    }

    @GetMapping("/api/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin-data");
    }

    // Used only by tests in the same package, not a public endpoint.
    int privateVisits() {
        return privateReads.get();
    }

    void resetForTests() {
        privateReads.set(0);
    }
}
```

Because the CORS filter completes preflight before invoking controllers, a valid preflight to `/api/private` **does not increment the counter**. Only an authenticated actual GET executes the handler and increments it. `AtomicInteger` here is purely a test aid, not real user state.

### 6.6. Starting the App

In the project directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell on Windows:

```powershell
.\gradlew.bat bootRun
```

Or using an installed compatible Gradle:

```bash
gradle bootRun
```

Assume the API runs at `http://localhost:8080`. Use HTTP on localhost for learning; **production must use HTTPS** whenever Basic auth, session cookies, or Bearer tokens are involved.

## 7. Testing Preflight with curl: CORS Without Identity

**Preflight with valid origin, GET, and Authorization header:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Expected: HTTP success (typically **200** in the demo), with `Access-Control-Allow-Origin: http://localhost:3000`, `Access-Control-Allow-Methods: GET`, `Access-Control-Allow-Headers: authorization`, and `Access-Control-Allow-Credentials: true`. **No `-u reader:...` or cookie is needed** in preflight. Curl does not enforce CORS itself or simulate full browser behavior; we use it to inspect responses.

**Origin not in allowlist:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: https://untrusted.example.invalid" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Expected: typically **403** from the CORS processor, with no valid `Access-Control-Allow-Origin` for that origin. If a request omits `Origin` and `Access-Control-Request-Method`, it is **not** a preflight anymore; the response may come from another security/handler path.

**Disallowed method:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: DELETE"
```

Expected: rejected by CORS because the policy allows only actual method GET. Merely adding `OPTIONS` to `allowedMethods` does not make DELETE valid.

**Disallowed header:**

```bash
curl -i -X OPTIONS "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-unlisted-header"
```

Expected: rejected by CORS because `X-Unlisted-Header` is not in `allowedHeaders`. Do not solve this by setting `allowedHeaders("*")` for all origins unless the app genuinely requires it.

### Windows PowerShell Note

In Windows PowerShell 5.1, `curl` can be an alias for `Invoke-WebRequest`. When using cURL syntax as shown above, invoke **`curl.exe`** on a single line (or use PowerShell backticks where appropriate; `\` line continuation is Unix shell syntax, not PowerShell). Example:

```powershell
curl.exe -i -X OPTIONS "http://localhost:8080/api/private" -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization"
```

## 8. Actual Request: Passing CORS Still Requires Authentication and Authorization

Call the endpoint with an allowed origin but **no credentials**:

```bash
curl -i "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000"
```

Expected: **401 Unauthorized** per HTTP Basic, typically with `WWW-Authenticate` and still carrying `Access-Control-Allow-Origin: http://localhost:3000` because CORS processes the actual request early. This is desirable: the browser can distinguish an authentication failure (401) from a CORS origin error.

Call with a valid user:

```bash
curl -i -u reader:local-test-password \
  "http://localhost:8080/api/private" \
  -H "Origin: http://localhost:3000"
```

Expected: **200 OK**, body:

```text
private-data
```

`reader` account accessing the admin endpoint:

```bash
curl -i -u reader:local-test-password \
  "http://localhost:8080/api/admin" \
  -H "Origin: http://localhost:3000"
```

Expected: **403 Forbidden** because the user is authenticated yet lacks `ROLE_ADMIN`, even though CORS for this origin is valid.

`admin` account:

```bash
curl -i -u admin:local-test-password \
  "http://localhost:8080/api/admin" \
  -H "Origin: http://localhost:3000"
```

Expected: **200 OK**, body:

```text
admin-data
```

**Security observation:** CORS does not decide who is an admin. A script on an allowed origin does not automatically gain access to `/api/admin`; it still needs valid credentials and authorities. Conversely, cURL can reach the API **without sending an Origin header** if given valid credentials: CORS is a browser policy, not a replacement for backend authentication/authorization.

### Status Summary

| Request | CORS | Security/HTTP | Expected HTTP status |
| --- | --- | --- | --- |
| OPTIONS preflight allowed origin + GET + Authorization | Pass, terminates early | Does not require login | 200 |
| OPTIONS preflight disallowed origin | Reject | No authz needed | 403 |
| OPTIONS preflight requested DELETE | Reject | No authz needed | 403 |
| GET /api/private, allowed origin, no credentials | Pass | HTTP Basic challenge | 401 |
| GET /api/private, allowed origin, reader | Pass | Authenticated | 200 |
| GET /api/admin, allowed origin, reader | Pass | Lacks ADMIN | 403 |
| GET /api/admin, allowed origin, admin | Pass | Has ADMIN | 200 |
| GET /api/private, no Origin, reader | Not CORS | Authenticated | 200 |
| GET /api/private, disallowed Origin | CORS rejects before auth | Body not read | Typically 403 |

On actual requests, the browser also validates the CORS response; seeing HTTP 200 in cURL **does not prove** a browser will let JavaScript on an unallowlisted origin read the body.

## 9. Automated Testing with WebTestClient: Look Beyond Status Codes

Goal: verify actual execution order using HTTP requests that inspect response headers, authn/authz, and controller side effects. The code below uses `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` to run security WebFilters inside a mock server.

**`src/test/java/example/corsorder/CorsOrderIntegrationTest.java`**:

```java
package example.corsorder;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CorsOrderIntegrationTest {

    private static final String UI = "http://localhost:3000";

    @Autowired
    ApplicationContext context;

    @Autowired
    ApiController api;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        api.resetForTests();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void validPreflightNeedsNoAuthenticationAndSkipsController() {
        client.options().uri("/api/private")
                .header("Origin", UI)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "authorization")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI)
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Credentials", "true");

        assertEquals(0, api.privateVisits());
    }

    @Test
    void preflightFromUnknownOriginIsRejected() {
        client.options().uri("/api/private")
                .header("Origin", "https://untrusted.example.invalid")
                .header("Access-Control-Request-Method", "GET")
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist("Access-Control-Allow-Origin");

        assertEquals(0, api.privateVisits());
    }

    @Test
    void preflightWithUnapprovedMethodIsRejected() {
        client.options().uri("/api/private")
                .header("Origin", UI)
                .header("Access-Control-Request-Method", "DELETE")
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(0, api.privateVisits());
    }

    @Test
    void preflightWithUnapprovedHeaderIsRejected() {
        client.options().uri("/api/private")
                .header("Origin", UI)
                .header("Access-Control-Request-Method", "GET")
                .header("Access-Control-Request-Headers", "x-unlisted")
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(0, api.privateVisits());
    }

    @Test
    void actualRequestWithoutCredentialsStillNeedsLogin() {
        client.get().uri("/api/private")
                .header("Origin", UI)
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI);

        assertEquals(0, api.privateVisits());
    }

    @Test
    void validReaderCanAccessPrivateApi() {
        client.get().uri("/api/private")
                .header("Origin", UI)
                .headers(h -> h.setBasicAuth(
                        "reader", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI)
                .expectBody(String.class).isEqualTo("private-data");

        assertEquals(1, api.privateVisits());
    }

    @Test
    void readerCannotAccessAdminEvenFromAllowedOrigin() {
        client.get().uri("/api/admin")
                .header("Origin", UI)
                .headers(h -> h.setBasicAuth(
                        "reader", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI);
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/api/admin")
                .header("Origin", UI)
                .headers(h -> h.setBasicAuth(
                        "admin", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-data");
    }

    @Test
    void requestWithoutOriginIsNotAWebCorsCheck() {
        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth(
                        "reader", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("private-data");
    }

    @Test
    void publicEndpointDoesNotRequireAuthentication() {
        client.get().uri("/api/public")
                .header("Origin", UI)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("Access-Control-Allow-Origin", UI)
                .expectBody(String.class).isEqualTo("public");
    }
}
```

Run command:

```bash
./gradlew test --tests example.corsorder.CorsOrderIntegrationTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.corsorder.CorsOrderIntegrationTest
```

**Expected result:** 10 tests PASS with files and dependencies matching the baseline. This is an **expected result based on the code**, not a compile/test log executed against a live project. Tests share the same controller instance and reset the counter in `@BeforeEach`; if tests run in parallel, isolate state or remove the shared counter to prevent cross-test races.

### Why Do These Tests Prove the Right Order?

- `OPTIONS` preflight **carries no Authentication**, still succeeds, and returns CORS response headers.
- The controller counter stays at 0: preflight terminates in the CORS layer without entering the business handler.
- Uncredentialed actual GET still returns **401**, proving a passing preflight does not bypass authentication.
- Actual GET from an allowed origin lacking the role still returns **403**, proving passing CORS does not bypass authorization.
- Disallowed origins/methods/headers are rejected by CORS.
- Requests without an `Origin` header still succeed with valid Basic auth, showing CORS is not an auth guard for non-browser clients.

A test that asserts only `OPTIONS=200` **is not enough**: a server could enable `permitAll OPTIONS` without emitting CORS headers, and the browser would still block the actual request. Always verify `Access-Control-Allow-*` headers and actual security separately.

## 10. Browser Interface: Credentials, Cookies, and Authorization

### 10.1. Different Origins Due to Different Ports

A frontend running on `http://localhost:3000` calling `http://localhost:8080` is **cross-origin**, even on the same machine. Browsers enforce CORS for JavaScript. In production, this is typically `https://ui.example.test` calling `https://api.example.test`; those two origins differ because their hostnames differ.

### 10.2. Fetch API Does Not Send All Credentials Automatically

`fetch()` defaults to `credentials: "same-origin"`. For cross-origin calls, browsers normally **do not send cookies** unless code sets `credentials: "include"` and cookie policies allow it. Regarding Basic authentication:

- An `Authorization` header added by frontend code normally triggers a preflight.
- If the browser has cached Basic credentials, behavior can depend on the browser and auth realm; do not base production designs on demo Basic auth.
- Never place fixed raw usernames/passwords in production frontend JavaScript; Basic auth must use HTTPS, and SPA/SSO flows should use an appropriate auth mechanism.

Illustrative example where the client receives credentials from an established architecture (no real token in this lesson):

```javascript
// Illustrative; authorizationHeader must be supplied securely by the application.
// Do not hardcode passwords/tokens in frontend code.
async function loadPrivate(authorizationHeader) {
  const response = await fetch("http://localhost:8080/api/private", {
    method: "GET",
    credentials: "include",
    headers: { Authorization: authorizationHeader }
  });

  if (response.status === 401) {
    throw new Error("Re-authentication required");
  }
  if (response.status === 403) {
    throw new Error("Insufficient permissions");
  }
  if (!response.ok) {
    throw new Error("HTTP error " + response.status);
  }
  return response.text();
}
```

This is an **illustrative JS snippet**, omitting how `authorizationHeader` is obtained and not a standalone app. The browser will preflight due to the `Authorization` header and execute GET once permitted. If the server returns 401 on preflight, JavaScript typically receives a network/CORS failure and **does not** enter the `response.status === 401` branch because the actual GET was never sent.

### 10.3. SameSite Can Block Cookies Even When CORS Allows Them

The CORS allowlist and cookie policies are two independent conditions:

- `Access-Control-Allow-Credentials: true` does not force the browser to send cookies.
- Cookies need proper `Domain`, `Path`, `Secure`, and `SameSite` attributes and must not be blocked by browser third-party cookie rules.
- CORS compares **origin** (scheme + host + port). `SameSite` cookies depend on **site**, which ignores port differences. Two localhost addresses on different ports are cross-origin yet usually same-site.
- In production across different registrable domains, `SameSite=Lax`/`Strict` cookies may be omitted on cross-site fetches even with a flawless CORS preflight.
- When true cross-site cookies are needed, `SameSite=None; Secure` and compatible browser policies are usually required. That is a security decision introducing extra CSRF exposure and third-party cookie restrictions.

**Do not conclude "CORS is right so cookies must be sent".** The Network tab shows preflight, the actual request, and sent cookies step by step; never share real cookies or session IDs.

## 11. Cookie-Based CORS Does Not Replace CSRF

A dangerous mistake is assuming an origin allowlist means state-changing requests are already safe.

CORS primarily governs whether JavaScript from another origin can send/read requests under browser rules. Yet a plain HTML form can submit a cross-origin POST without needing to read the response. If the browser automatically attaches session cookies, the server still needs **CSRF** protection on POST/PUT/PATCH/DELETE as designed.

In Spring Security WebFlux, `CsrfWebFilter` is enabled by default. When adding write endpoints:

- Keep CSRF enabled if authentication uses browser sessions/cookies or ambient credentials.
- Supply the CSRF token to the frontend over a same-origin or properly protected channel.
- Send the token in the field/header supported by the backend's CSRF repository and request handler.
- Never use `.csrf(csrf -> csrf.disable())` just because OPTIONS preflight returned 403: preflights are solved with **CORS ordering**, not by disabling protection on state-changing requests.
- A request from an allowed `Origin` can still receive **403 CSRF** if its token is missing; that is distinct from a CORS 403 or authorization 403.

Because the demo above **has only GET endpoints**, keeping CSRF at its default does not disrupt the primary routes. If you add POSTs, design dedicated tests: preflight succeeds, while the actual POST requires both authentication and a valid CSRF token. When the actual POST lacks a token, CORS passes yet CSRF denies.

### Comparing Three Kinds of 403 Errors

| Cause | Which request is blocked? | How to verify |
| --- | --- | --- |
| CORS policy disallows origin/method/header | Preflight or actual CORS request | OPTIONS status, `Access-Control-Allow-Origin`, CORS logs |
| Invalid or missing CSRF token | Unsafe actual request | CSRF logs, token/repository, proper cookie handling |
| Authorization lacks role/permission | Actual request after authentication | Principal, authorities, matchers/ACL |

A `403` response **does not explain by itself** whether it is CSRF, CORS, or missing permissions. Avoid exposing sensitive security internals to clients; use correlation IDs and safe structured logs to tell them apart internally.

## 12. When to Use Standalone CorsWebFilter Instead of ServerHttpSecurity.cors?

Spring Framework provides `org.springframework.web.cors.reactive.CorsWebFilter`, which can be registered as a bean and ordered in the **outer WebFilter chain**.

If choosing the **alternative approach**, an illustrative snippet:

```java
// Fragment used as an ALTERNATIVE; do not run alongside
// the same CORS policy already managed by .cors(...).
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
CorsWebFilter corsWebFilter(UrlBasedCorsConfigurationSource source) {
    return new CorsWebFilter(source);
}
```

Required imports are `org.springframework.web.cors.reactive.CorsWebFilter`, `org.springframework.core.Ordered`, and `org.springframework.core.annotation.Order`. This is only a **fragment** inside a `@Configuration`; since the main demo project already configures CORS in `ServerHttpSecurity`, **do not add this bean**.

Important notes:

1. A standalone filter must be ordered **ahead of Spring Security's WebFilter proxy**, not merely ahead of controllers.
2. If you also enable `.cors(...)` with a different source, you risk duplicate response headers, conflicting policies, and hard-to-explain behavior.
3. With functional routes or an API gateway, pick an early position covering all routing, not just one controller.
4. Even when the filter is ordered correctly, the **actual request** must still pass authentication and authorization.
5. Never use `FilterRegistrationBean` or Servlet `CorsFilter` in pure WebFlux.

**Lesson preference:** CORS integration via `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))`, because Spring Security automatically places `CorsWebFilter` at `SecurityWebFiltersOrder.CORS`, simplifying testing and avoiding manual WebFilter order guesswork.

## 13. @CrossOrigin and WebFluxConfigurer May Fall Short When Security Runs First

Spring WebFlux provides CORS support at `HandlerMapping` and via annotations:

```java
// Example illustrating annotation scope only; do not add to the main demo.
@CrossOrigin(origins = "http://localhost:3000")
@GetMapping("/api/report")
public Mono<String> report() {
    return Mono.just("report");
}
```

However, `@CrossOrigin` belongs to controller/`HandlerMapping` CORS mapping. If a security WebFilter already rejected `OPTIONS` for lacking authentication **before handler resolution**, this annotation cannot rescue the preflight.

Similarly:

```java
// Fragment for Spring WebFluxConfigurer if choosing this approach.
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:3000")
            .allowedMethods("GET")
            .allowedHeaders("Authorization", "Content-Type")
            .allowCredentials(true);
}
```

This configures the **WebFlux layer**, which is no guarantee that security lets preflight through. If used together, verify that Spring Security has proper CORS integration and policies do not clash. When an application has a single API policy, **avoid carelessly mixing all three configuration sites**.

### Special Case: OPTIONS Does Not Match a GET Controller Matcher

A preflight `OPTIONS /api/private` asks about an intended GET. A CORS filter matching URL pattern `/api/**` handles it even though the controller only declares `@GetMapping`. If you restrict a security chain with a matcher **requiring method GET**, the `OPTIONS` preflight will miss that chain and fall into another chain. This is a subtle bug in applications with multiple `SecurityWebFilterChain`s.

## 14. Multiple SecurityWebFilterChains, API Gateways, and Reverse Proxies

### 14.1. Multiple Chains by Path

When separating an API and a web UI:

```text
SecurityWebFilterChain @Order(1): /api/**
  - CorsSpec: API CORS policy
  - HTTP Basic / Bearer authentication
  - API authorization

SecurityWebFilterChain @Order(2): catch-all
  - Browser form login or public/static
  - Web UI policy
```

A common pitfall is making the first chain matcher accept only `GET /api/**`, causing `OPTIONS` preflight to fall through to the catch-all chain that demands login. Match the API chain **by path**, without restricting to `GET` only, and define allowed methods inside **`CorsConfiguration`**. If multiple chains need distinct CORS setups, verify which chain handles `OPTIONS`. An independent CORS filter ahead of security can also be a valid strategy when sharing a common policy.

**Do not** define two catch-all chains expecting requests to traverse both; Spring Security picks the first matching chain by matcher/order.

### 14.2. Reverse Proxies Handling OPTIONS

An Nginx, gateway, or CDN may respond to preflight before the app, or block `OPTIONS` before it reaches Spring. If you delegate CORS to a proxy:

- Use **one unified policy source** across the gateway and backend.
- Never reflect arbitrary Origins alongside `Access-Control-Allow-Credentials: true`.
- Allow the exact paths/methods/headers; protect response caches with `Vary`.
- Ensure the proxy does not strip `Access-Control-Allow-*` headers from 401/403/500 responses sent by the backend.
- Never let the proxy blindly answer "OPTIONS=200" when the backend forbids the actual method or header.
- Configure trusted proxies and forwarded headers, especially scheme/host/port, since origins depend on the scheme.

If requests never reach the app, tweaking `SecurityWebFilterChain` will not fix preflight. Use gateway logs, access logs, and tracing to see which component produced the response.

### 14.3. Spring Cloud Gateway and Route Predicates

A gateway route matching only HTTP method GET will **not match an `OPTIONS` preflight**. Some Spring Cloud Gateway WebFlux releases provide a global CORS option for the simple URL handler mapping such as `add-to-simple-url-handler-mapping`; check the exact property namespace for your gateway version. Never copy YAML configuration from a different release without verifying it. Route CORS metadata must also align with paths/methods so preflight does not hit 404 or 401.

## 15. Safe CORS Policy: Never Open More Than Needed

| Property | Meaning | Principle |
| --- | --- | --- |
| `allowedOrigins` | Allowed origins | Explicit list including scheme/host/port |
| `allowedOriginPatterns` | Pattern-based origin matching | Use only when needed; audit wildcards carefully |
| `allowedMethods` | Permitted actual HTTP methods | Only the GET/POST/PUT/... actually needed |
| `allowedHeaders` | Headers JS is allowed to send | Authorization/Content-Type and required custom headers |
| `exposedHeaders` | Extra response headers JS may read | Only business headers the client needs |
| `allowCredentials` | Browser may send credentials and read credentialed responses | Enable only for trusted origins, never wildcard `*` |
| `maxAge` | Browser preflight cache duration | Unrelated to token/session lifetimes |
| `Vary` | How caches key responses by Origin/method/headers | Must be right when CDN/proxy caches are present |

### Wildcards and Credentialed Requests

Per Spring Framework, never use `allowedOrigins("*")` with `allowCredentials(true)`. If misconfigured, the framework rejects the config or request because it cannot determine a valid `Access-Control-Allow-Origin` for a credentialed response.

If multiple subdomains are genuinely required, use an explicit list of origins or a tightly scoped `allowedOriginPatterns`. Never reflect every client-supplied `Origin` with `Access-Control-Allow-Credentials: true`—that could let an untrusted website read responses under the user's identity.

### "Lookalike" Origins That Differ

- `http://localhost:3000` differs from `http://localhost:8080`.
- `https://ui.example.test` differs from `http://ui.example.test`.
- `https://ui.example.test` differs from `https://api.example.test`.
- Browsers typically omit `Origin` on normal same-origin GETs; a missing `Origin` **does not mean** a request is malicious, and servers must not use CORS to authenticate non-browser clients.

**CORS is not a backend access-control list.** CORS is enforced primarily by browsers; callers using cURL or other servers can omit or fake `Origin`. Every sensitive API must enforce real authentication and authorization.

## 16. Symptom-Based Troubleshooting Table

| Symptom | Likely diagnosis | Remedy |
| --- | --- | --- |
| Preflight OPTIONS 401 | Security demands login before CORS, or gateway blocks it | Order CORS before authentication; check chains/proxy |
| Preflight OPTIONS 302 to /login | Form login entry point intercepts OPTIONS | Integrate `CorsWebFilter` early; do not redirect preflight |
| OPTIONS 200 yet browser reports CORS error | Missing/wrong ACA-Origin, Methods, or Headers | Check response headers and actual origin/method/headers |
| OPTIONS 403 | Origin, requested method, or requested header denied by CORS | Match allowlist; do not disable authentication |
| OPTIONS 404 | Route/gateway/HandlerMapping does not match OPTIONS | Handle CORS early; check route predicates |
| OPTIONS 405 | Controller/gateway handles OPTIONS instead of CORS preflight | Check filter and requested method |
| Valid OPTIONS yet actual GET 401 | Missing/expired credentials or wrong auth scheme | Fix authentication, do not relax CORS |
| Valid OPTIONS yet actual GET 403 | Missing role or authorization policy denial | Check authorities, rules, and principal |
| Actual POST 403 after passing preflight | Could be CSRF, authorization, or business rule | Distinguish CSRF token vs. role; inspect logs |
| CORS allowed yet cookies not sent | Fetch credentials mode, cookie SameSite/Path/Domain/Secure | Inspect Network and Application cookies |
| `Authorization` header rejected by preflight | Missing from `allowedHeaders` | Add the specific header with proper scope |
| Edited `@CrossOrigin` yet OPTIONS still 401 | Security blocks before HandlerMapping | Use `ServerHttpSecurity.cors(...)` or early `CorsWebFilter` |
| MVC `CorsFilter` config in a WebFlux app | Wrong stack/bean unused | Import `org.springframework.web.cors.reactive` |
| Two `CorsWebFilter`/CORS beans with overlapping policy | Duplicate headers, unpredictable behavior | Pick one clear integration point |
| 401/403 lacks ACAO | CORS runs too late or proxy strips headers | Ensure CORS runs before auth; check gateway |
| `allowCredentials=true` + wildcard `*` | Invalid/unsafe policy | Allowlist explicit origins |
| Only `https://...` allowlisted while local uses `http://...` | Scheme mismatch in origin | Set exact dev origin and production HTTPS |
| Tests assert only HTTP 200 | Fails to verify actual browser policy | Assert ACA headers and actual auth checks |
| CORS passes yet API client leaks data | Missing backend authorization | Add role/ACL/tenant checks |
| Preflight cache masks config changes | Browser reuses cached preflight | Test with fresh browser profile/URL and reasonable `maxAge` |
| Cache/CDN serves wrong-origin ACAO | Missing `Vary` or wrong cache key | Ensure `Vary: Origin` and inspect CDN config |

### Recommended Investigation Sequence

1. Open DevTools → **Network**, filter `OPTIONS` and the API URL; confirm whether preflight occurred.
2. Check preflight **Request Headers**: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. Check preflight **Status and Response Headers**: ACA-Origin, ACA-Methods, ACA-Headers, ACA-Credentials, Vary.
4. If preflight passed, inspect the **actual GET/POST** to verify whether credentials were sent, its actual status, and CORS headers.
5. Check application logs for CORS rejections, authentication challenges, access denials, or CSRF rejections—never log passwords, tokens, or cookies.
6. Identify which layer blocked the request: browser, gateway, Spring `CorsWebFilter`, Security WebFilter, or controller.
7. Only after pinpointing the failing layer should you edit configuration; never disable security wholesale or open wildcards just to "make requests pass".

## 17. Pre-Production Review Checklist

1. CORS runs **before authentication and authorization** for preflight requests to cross-origin APIs.
2. Valid `OPTIONS` needs no login, cookie, or Basic header and does not reach controllers.
3. Origins, actual methods, and requested headers are checked against an environment-specific allowlist.
4. Actual requests still enforce authentication, authorization, and CSRF as appropriate.
5. Actual 401/403 responses carry proper CORS headers so trusted frontends can read statuses without loosening policy.
6. `allowedOrigins("*")` is never combined with `allowCredentials(true)`; arbitrary Origins are never reflected blindly.
7. Cookie `SameSite`/`Secure`/`HttpOnly`/`Domain`/`Path` match your frontend-backend topology; CORS does not force cookies through.
8. Do not abuse `OPTIONS permitAll` instead of CORS config; never redirect preflights to login.
9. One component owns the CORS policy; avoid accidentally pairing a standalone `CorsWebFilter` with a conflicting security `CorsSpec`.
10. When using multiple `SecurityWebFilterChain`s, `OPTIONS` preflights match the chain/path with CORS configured.
11. Gateways/proxies/CDNs do not block `OPTIONS`, do not inject arbitrary ACA headers, and honor `Vary`.
12. Test valid preflights, invalid origins/methods/headers, actual 401, actual 403, actual 200, and controller side effects.
13. For non-browser clients, backend authorization still applies even without an `Origin` header.
14. Every policy change is reviewed, tested, and monitored per origin and endpoint to prevent over-exposure.
15. Never write raw passwords, session cookies, `Authorization` headers, or CSRF tokens to error logs.

## 18. Practice Exercises

1. Remove `.cors(...)` from the Security chain while keeping `.authorizeExchange(...)`. Send an `OPTIONS` preflight and observe the status/headers. Explain the error by filter/handler.
2. Add `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` still without a CORS source; demonstrate that passing OPTIONS (if handled) **is not enough** for browsers to read actual requests when ACA headers are absent.
3. Switch the frontend origin to `http://127.0.0.1:3000` while keeping the `http://localhost:3000` allowlist. Confirm browsers treat them as different origins and CORS rejects it.
4. Add `X-Trace-Id` to the request; test before and after adding it to `allowedHeaders`. Avoid wildcards when explicit listing works.
5. Add `POST /api/actions`; allow method `POST` in CORS, keep CSRF if using session cookies, and write separate tests for passing preflight vs. actual POST missing/having a token.
6. Add an `/api/**` chain and a browser chain. Match the API chain strictly by path and prove `OPTIONS` preflights also select the right chain.
7. Migrate the HTTP Basic demo to Bearer JWT; verify preflight still carries **no Authorization**, while the actual request sends Bearer and must still satisfy scopes/authorities.
8. Place the app behind a gateway; determine whether the gateway or backend answers `OPTIONS` using response headers and tracing. Avoid two conflicting CORS policies.
9. Use DevTools to compare a simple GET without preflight against a GET with `Authorization` that requires preflight.
10. Change `allowCredentials(true)` to `false`; describe the impact on JavaScript `credentials:"include"` versus explicitly attached `Authorization` headers.
11. Build a QA matrix covering origin, requested method, requested headers, authentication status, and resource permissions; do not test only happy paths.
12. Explain why the server must never treat the `Origin` header as proof of a trusted user, especially against server-to-server scripts.

## Summary

**The proper order for a WebFlux application serving a cross-origin frontend is: CORS is evaluated first → valid preflights terminate without identity → actual requests proceed through authentication, authorization, and CSRF as appropriate.**

Spring Security 6.5 supports this via `ServerHttpSecurity.cors(cors -> cors.configurationSource(...))`, placing `CorsWebFilter` at `SecurityWebFiltersOrder.CORS`. A 200 preflight with valid headers says nothing about data access permissions; the actual GET/POST must still pass security policies. Conversely, a 401 or login redirect on preflight indicates CORS integration or filter ordering is likely misconfigured. Keep allowlists tight, verify with both browsers and `WebTestClient`, keep CORS separate from CSRF, and never substitute CORS for authentication or authorization.

## Official References

- [Spring Security 6.5 — CORS in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — ServerHttpSecurity.CorsSpec Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html)
- [Spring Security 6.5 — SecurityWebFiltersOrder](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — CorsWebFilter API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Fetch credentials mode](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials)
- [Spring Cloud Gateway — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html)
