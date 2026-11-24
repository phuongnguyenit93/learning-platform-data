# Testing CORS Preflight, Disallowed Origins, and Credentials

**Module:** Spring Security – reactive (Spring WebFlux)  
**Group:** HTTP Testing  
**Topic:** Testing `OPTIONS` CORS preflight, disallowed origins, and requests with credentials using `WebTestClient`, `curl`, and browsers; distinguishing CORS responses from authentication, authorization, CSRF, and cookie mechanics.

## 1. Key Takeaways

**CORS does not grant API access.** CORS is a rule enforced by **browsers** to decide which origins' JavaScript may read cross-origin responses. The server must still authenticate and authorize every request, including requests without an `Origin` header or requests sent by tools such as `curl`.

**Preflight is not the actual request:** For a GET carrying an `Authorization` header, browsers normally send an `OPTIONS` request first, including `Origin`, `Access-Control-Request-Method: GET`, and `Access-Control-Request-Headers: authorization`. This preflight **does not carry user cookies or `Authorization` credentials**. Only when CORS is accepted does the browser send the actual GET with credentials (if any). Therefore, Spring Security WebFlux must handle CORS **before** authentication; never reject `OPTIONS` just because no user session exists yet.

**Credentialed CORS demands an exact allowlist:** If the server returns `Access-Control-Allow-Credentials: true`, then `Access-Control-Allow-Origin` must return a **specific allowed origin**, never the wildcard `*`. `credentials:"include"` neither authenticates a user automatically nor forces browsers to send cookies if `SameSite`/third-party policies block them.

**HTTP tests are not browser tests:** `WebTestClient` and `curl` let you set `Origin` arbitrarily and read HTTP status/headers/bodies even for disallowed origins. They **do not enforce** browser CORS rules. Test HTTP integration and browser behavior **separately** to avoid misreading a `200` response as proof that JavaScript can read the body.

## 2. Four layers of a CORS request

| Layer | Question | Observed outcome |
| --- | --- | --- |
| CORS preflight | Are origin, method, and request headers allowed? | `200` + ACAO/ACAM/ACAH/ACAC if allowed; Spring's `DefaultCorsProcessor` typically returns `403` if CORS is invalid |
| Browser enforcement | Do response ACAO/ACAC match the credential mode? | JavaScript receives `Response` or a CORS/`TypeError`; sometimes the HTTP network call still returned 200 |
| Authentication | Does the actual request carry valid Basic/Bearer/session credentials? | `401` if missing/invalid, sometimes form login redirect `302` |
| Authorization and CSRF | Is the principal allowed to act; does a mutation carry a valid CSRF token? | `403` when missing permissions/CSRF |

**Do not conflate** a `403` from the CORS processor with a `403` from authorization or CSRF. Debug by inspecting `Origin`, `Access-Control-Request-Method`, ACAO/ACAC, status, authentication context, and filter ordering. In multi-tenant systems, tenant verification can never rely on `Origin` alone.

### 2.1. What exactly is an Origin?

An Origin is the tuple `scheme + host + port`. Compare:

```text
https://app.example.test         ALLOWED in lesson
http://app.example.test          DENIED: different scheme
https://app.example.test:8443    DENIED: different port
https://evil.example.test        DENIED: different host
null                             DENIED: not an allowlisted domain
https://app.example.test.evil    DENIED: different domain
```

Never use `String.endsWith("example.test")` to check origins: it can accept domains you do not own. `Origin: null` commonly appears in sandboxed/file/data contexts; do not trust it by default. Browsers set `Origin` automatically on `fetch`, whereas non-browser tools can send any value, so `Origin` is **not an identity**.

### 2.2. HTTP headers to inspect

| Header | Direction | Purpose |
| --- | --- | --- |
| `Origin` | Request | Origin of JavaScript/browser |
| `Access-Control-Request-Method` | **Preflight request** | Intended actual method |
| `Access-Control-Request-Headers` | **Preflight request** | Intended request header names, never raw token values |
| `Access-Control-Allow-Origin` | Response | Allowed origin, or `*` for appropriate non-credentialed cases |
| `Access-Control-Allow-Methods` | Preflight response | Allowed actual methods |
| `Access-Control-Allow-Headers` | Preflight response | Allowed request headers |
| `Access-Control-Allow-Credentials` | Response | Allows browser to expose credentialed CORS response |
| `Access-Control-Expose-Headers` | Actual response | Extra response headers readable by JavaScript |
| `Access-Control-Max-Age` | Preflight response | Duration the browser may cache the preflight result |
| `Vary` | Response | Separates caches by `Origin` and request method/headers when applicable |
| `Authorization` | **Actual request** | Basic/Bearer credentials, absent on standard browser preflight |
| `Cookie` | **Actual request** | Session/CSRF cookies if permitted by browser; absent on standard preflight |

Do not send `Access-Control-Allow-Credentials` on a **request** thinking the server will enable credentialed mode. It is a response header returned by the server. Do not expect `Set-Cookie` to be readable from JavaScript via exposed headers; it is a forbidden response header in Fetch.

## 3. Differences between preflight and actual GET

JavaScript from `https://app.example.test`:

```javascript
// accessToken is obtained through the app's security mechanism;
// never hardcode it or put real tokens into URLs/logs.
fetch("https://api.example.test/api/me", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
```

Because of the `Authorization` header, the browser sends a preflight first:

```http
OPTIONS /api/me HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

There is **no** `Authorization: Bearer ...` or `Cookie: SESSION=...` in `OPTIONS`. The CORS processor may respond:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Illustrative example; header order and `Vary` formatting may differ. The browser then sends the actual GET with Bearer. The actual request may return:

- `200` if the token is valid and authorized.
- `401` if the token is missing or invalid.
- `403` if the principal is authenticated but lacks sufficient authority.
- `403` from the CORS processor if `Origin` is invalid in this lesson's Spring config.

**Preflight 200 does not mean actual 200.** Also, a simple GET without custom headers may **skip preflight**, yet the actual response still needs the proper ACAO for JavaScript to read the body.

### 3.1. `OPTIONS` must precede Spring Security authentication

The Spring Security WebFlux reference states that CORS must be processed before Security because preflight carries no login cookies. If the server demands authentication before handling `OPTIONS`, `OPTIONS` typically fails with `401` or `302 /login`, preventing the browser from sending the actual request. Never fix this by calling `permitAll("/api/**")`, which exposes protected endpoints.

In WebFlux, use `CorsConfiguration` with `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` and `ServerHttpSecurity.cors`, or a properly ordered `CorsWebFilter`. **Do not copy Servlet imports** (such as `org.springframework.web.cors.UrlBasedCorsConfigurationSource`) into a WebFlux program.

Allowing `OPTIONS` via `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` alone **does not replace** the CORS processor: it does not emit ACAO, ACAM, ACAH, or validate allowed origins. Always assert both status and headers.

### 3.2. Actual requests without `Origin`

`curl -u viewer:viewer-pass http://localhost:8080/api/me` can receive HTTP 200 because Basic credentials are valid, **without ACAO**, which is completely normal. CORS is not a firewall blocking HTTP clients; non-browser clients can omit or forge `Origin`. Authentication and authorization must work accurately even when `Origin` is absent.

## 4. Credentials, cookies, and CSRF

### 4.1. Fetch credential modes

| JavaScript fetch | Cross-origin cookies auto-sent? | What do server and browser need? |
| --- | --- | --- |
| `credentials:"omit"` | No per credential mode | Response needs suitable ACAO if JS reads it |
| `credentials:"same-origin"` (default) | Not sent to other origins | Cross-origin API may 401 even if cookies exist |
| `credentials:"include"` | Possibly, **if** cookie policy allows | Exact ACAO + ACAC true; still subject to `SameSite`/Secure/domain/path/third-party-cookie policy |
| Explicit JS `Authorization: Bearer ...` | Does not need cookies for Authorization | Preflight normally declares request header `authorization`; token still requires validation |
| `HttpOnly` cookie | JS cannot read cookie value | Browser may auto-send cookie if policy allows; server must check CSRF |
| `SameSite=None; Secure` cookie | Usable for cross-site HTTPS when allowed by browser | Does not bypass third-party cookie blocking or partitioning policies |

`credentials:"include"` **does not guarantee** cookies were sent. Inspect DevTools Network/Application tabs to see why a cookie was blocked, such as `SameSite`, `Secure`, `Domain`, `Path`, expiry, or user privacy settings.

### 4.2. Wildcards are invalid with credentials

```java
CorsConfiguration invalid = new CorsConfiguration();
invalid.setAllowedOrigins(List.of("*"));
invalid.setAllowCredentials(true);
// checkOrigin / validation may throw IllegalArgumentException.
```

For credentialed responses, browsers block JavaScript from reading if ACAO is `*`. The fix is an explicit allowlist:

```java
config.setAllowedOrigins(
    List.of("https://app.example.test"));
config.setAllowCredentials(true);
```

`allowedOriginPatterns` supports dynamic origin sets, which does not make pattern `*` safe: with cookie auth, reflecting any origin can let an attacker read sensitive responses when the browser holds an active session. Design a tenant-origin registry with domain ownership verification, HTTPS, and explicit domain lists.

### 4.3. CORS does not replace CSRF

Even when a malicious site cannot **read** responses, it can still **trigger** certain auto-credentialed requests (especially forms/cookies) unless the server defends against it. POST/PUT/DELETE require CSRF protection when using session cookies or cached Basic credentials. `SameSite` is defense-in-depth, not a replacement for CSRF controls.

In this lab, we use demo HTTP Basic while **keeping Spring Security's default CSRF enabled**, giving two separate checks:

- Preflight `OPTIONS` for POST passes without a CSRF token because it is not a business mutation.
- Actual `POST /api/action` with valid Basic but **no CSRF** returns `403`.
- Actual POST with valid Basic and valid test `csrf()` returns `200`.

`csrf()` from `spring-security-test` only tests Spring Security filter behavior; it does **not** prove real CSRF cookies work in Chrome/Safari. Complete browser QA by testing session cookies, token retrieval, and header forwarding per the real app design.

## 5. Designing an unambiguous test matrix

Example configuration:

```text
Allowed Origin:  https://app.example.test
Allowed Methods: GET, POST
Allowed Headers: Authorization, Content-Type, X-CSRF-TOKEN
Allow Credentials: true
CORS Paths: /api/**
GET /public: public, CORS not enabled on this route
GET /api/me: Basic authentication
POST /api/action: Basic authentication + CSRF
```

| Scenario | Request to test | Expected with Spring CORS processor |
| --- | --- | --- |
| Valid GET preflight | OPTIONS, allowed Origin, ACRM GET, ACRH authorization, **no auth** | 200, exact ACAO, ACAC true, right ACAM/ACAH |
| Valid POST preflight | OPTIONS `/api/action`, ACRM POST, ACRH content-type,x-csrf-token | 200, no CSRF token required |
| Evil preflight | OPTIONS, evil Origin | 403, no ACAO |
| Null origin preflight | OPTIONS, Origin `null` | 403, no ACAO |
| Wrong scheme/port | OPTIONS, `http` instead of `https` or `:8443` | 403 |
| Disallowed method | OPTIONS, ACRM DELETE | 403 |
| Disallowed header | OPTIONS, ACRH `x-admin` | 403 |
| Actual GET no Basic | Allowed Origin, GET | 401, ACAO still present |
| Actual GET valid Basic | Allowed Origin, GET | 200, ACAO/ACAC, DTO body |
| Actual GET invalid Basic | Allowed Origin, GET | 401 |
| Actual GET evil origin + Basic | Evil Origin, GET | 403 from CORS, no ACAO |
| Actual GET no Origin + Basic | No Origin, GET | 200, no ACAO |
| Actual GET fake cookie, no Basic | Allowed Origin, GET | 401 |
| Actual POST Basic, no CSRF | Allowed Origin, POST | 403 |
| Actual POST Basic + test CSRF | Allowed Origin, POST | 200 |
| Actual POST evil + test CSRF | Evil Origin, POST | 403 from CORS, no ACAO |

**Status does not tell the whole story:** another framework's CORS processor might return a different status for an invalid origin; the core requirement is that browsers cannot read responses unless ACAO permits them. When testing **this chosen Spring WebFlux implementation**, `403` from `DefaultCorsProcessor` is the expected outcome.

## 6. Java 17+ Spring Boot WebFlux project to run tests

**Baseline versions in example:** Java 17+, Maven 3.9+, Spring Boot 3.5.7, Spring Security 6.5.x via Boot BOM. The goal is a self-contained runnable demo, not prescribing a permanent production version. Upgrade to supported, patched versions in real deployments.

Directory tree:

```text
cors-webflux-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/cors/
    │   │   ├── CorsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/cors/
        ├── CorsHttpTests.java
        └── CorsPolicyUnitTests.java
```

Do not use `spring-boot-starter-web` because the lesson needs reactive CORS (`CorsWebFilter`/`ServerHttpSecurity`), not Servlet MVC.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>cors-webflux-tests</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
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

`src/main/resources/application.properties`:

```properties
spring.application.name=cors-webflux-tests
server.port=8080
```

`src/main/java/demo/cors/CorsApplication.java`:

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
```

### 6.1. `SecurityConfig.java`: CORS allowlist with credentials

`src/main/java/demo/cors/SecurityConfig.java`:

```java
package demo.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    static final String ALLOWED_ORIGIN =
        "https://app.example.test";

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(ALLOWED_ORIGIN));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-CSRF-TOKEN"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setAllowCredentials(true);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}viewer-pass")
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(viewer);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers("/api/**")
                    .authenticated()
                .anyExchange().denyAll())
            .cors(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // Do not disable CSRF; keep default.
            .build();
    }
}
```

**Explanation:**

1. `UrlBasedCorsConfigurationSource` is in the `reactive` package, the right type for Spring Security WebFlux. It is a single source bean wired through `.cors(withDefaults())`; **do not simultaneously register another `CorsWebFilter` bean** or broad `@CrossOrigin` annotations with unclear precedence.
2. The sole allowed origin is `https://app.example.test`, avoiding wildcards with `allowCredentials(true)`.
3. Allowed methods include only GET and POST; `OPTIONS` is the preflight method querying the actual method and does not need to be listed to allow GET/POST.
4. `Authorization`, `Content-Type`, and `X-CSRF-TOKEN` are the allowed preflight request headers; avoid `allowedHeaders("*")` since it easily hides policy gaps.
5. `X-Request-Id` is readable by JavaScript after the actual response; never expose cookie/token headers globally.
6. `maxAge=600` lets browsers cache preflight results, though browsers may apply lower caps. When changing production policies, test/observe preflight caching.
7. `httpBasic` is a fixture, not representing OAuth2 Login; `NoOpServerSecurityContextRepository` avoids storing security context in sessions. CSRF stays enabled by default for POST even when Basic succeeds.
8. `anyExchange().denyAll()` denies out-of-scope routes. Never `permitAll` the API just to make preflight pass.
9. Password `{noop}viewer-pass` is strictly for demo use, never production. With browsers and HTTP Basic, HTTPS is mandatory; Basic credentials can be cached by browsers, which is why **CSRF should not be dropped** without threat analysis.

### 6.2. `DemoController.java`: observing real responses

`src/main/java/demo/cors/DemoController.java`:

```java
package demo.cors;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    public record Me(String username) {}
    public record Action(String status) {}

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicRoute() {
        return Mono.just("public");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Me>> me(Principal principal) {
        return Mono.just(ResponseEntity.ok()
            .header("X-Request-Id", "demo-123")
            .body(new Me(principal.getName())));
    }

    @PostMapping(value = "/api/action",
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Action> action() {
        // No real DB write. Used to test Security/CSRF.
        return Mono.just(new Action("accepted"));
    }
}
```

There is no `Origin`-checking code inside the controller: Spring's CORS processor runs beforehand. The `Principal` for `GET /api/me` comes from Spring Security Basic authentication; never read usernames from query parameters or `Origin`. POST is an unsafe method, so CSRF testing remains meaningful even though the demo does not write to a database.

## 7. Standalone Java 17 CLI: exact origin matching

Before testing Spring, you can run a plain JDK 17 program as a reminder that origin matching **is not** partial domain matching. This program only models an allowlist and does **not** reproduce the full Fetch/CORS processor.

Save `OriginPolicyDemo.java`:

```java
import java.util.Set;

public class OriginPolicyDemo {
    static final Set<String> ALLOWED =
        Set.of("https://app.example.test");

    static boolean allowed(String origin) {
        return ALLOWED.contains(origin);
    }

    public static void main(String[] args) {
        System.out.println("allowed=" +
            allowed("https://app.example.test"));
        System.out.println("wrongScheme=" +
            allowed("http://app.example.test"));
        System.out.println("wrongPort=" +
            allowed("https://app.example.test:8443"));
        System.out.println("evil=" +
            allowed("https://evil.example.test"));
    }
}
```

Run:

```bash
javac OriginPolicyDemo.java
java OriginPolicyDemo
```

**Exact stdout:**

```text
allowed=true
wrongScheme=false
wrongPort=false
evil=false
```

In Spring, use `CorsConfiguration.checkOrigin` to test the configured policy; in browsers, Origins also apply default-port normalization and URL rules. Never replace the framework's CORS implementation with a contextless `Set.contains` if the app has dynamic origins.

## 8. HTTP tests with `WebTestClient` and Spring Security reactive

We use `@SpringBootTest(webEnvironment = MOCK)` + `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` to run the full WebFlux filter chain **without opening a port**. `spring-security-test` supplies `csrf()` for test mutations. Never use Servlet `MockMvc` or `SecurityMockMvcRequestPostProcessors.csrf` for a WebFlux application.

**Important:** `WebTestClient` does not automatically issue `OPTIONS` when you call GET with `Origin`/`Authorization`. Browsers may auto-preflight; in tests you must **send `OPTIONS` explicitly** and test the actual GET separately.

`src/test/java/demo/cors/CorsHttpTests.java`:

```java
package demo.cors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class CorsHttpTests {

    private static final String ALLOWED =
        "https://app.example.test";
    private static final String EVIL =
        "https://evil.example.test";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec preflight(
            String origin, String method, String headers) {
        return client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, origin)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                method)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                headers)
            .exchange();
    }

    @Test
    void validPreflightNeedsNoAuthentication() {
        preflight(ALLOWED, "GET", "authorization")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true")
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                v -> assertTrue(v.contains("GET")))
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                v -> assertTrue(
                    v.toLowerCase().contains("authorization")));
    }

    @Test
    void preflightHasCacheAgeAndVary() {
        preflight(ALLOWED, "GET", "authorization")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_MAX_AGE, "600")
            .expectHeader().value(
                HttpHeaders.VARY,
                v -> assertTrue(v.contains("Origin")));
    }

    @Test
    void postAndCsrfHeaderPreflightPassesWithoutCsrf() {
        client.options().uri("/api/action")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange().expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED);
    }

    @Test
    void unknownOriginPreflightIsRejected() {
        preflight(EVIL, "GET", "authorization")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void nullOriginPreflightIsRejected() {
        preflight("null", "GET", "authorization")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void wrongSchemeIsNotTheSameOrigin() {
        preflight("http://app.example.test", "GET",
            "authorization").expectStatus().isForbidden();
    }

    @Test
    void wrongPortIsNotTheSameOrigin() {
        preflight("https://app.example.test:8443", "GET",
            "authorization").expectStatus().isForbidden();
    }

    @Test
    void disallowedDeleteMethodIsRejected() {
        preflight(ALLOWED, "DELETE", "authorization")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void disallowedCustomHeaderIsRejected() {
        preflight(ALLOWED, "GET", "x-admin")
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void allowedCorsDoesNotAuthenticateActualGet() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .exchange().expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true");
    }

    @Test
    void correctBasicActualRequestReturns200AndCorsHeaders() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true")
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                v -> assertTrue(v.contains("X-Request-Id")))
            .expectBody()
            .jsonPath("$.username").isEqualTo("viewer");
    }

    @Test
    void invalidBasicPasswordStillReturns401() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "incorrect"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void evilActualOriginDeniedEvenIfBasicCorrect() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, EVIL)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void noOriginWithCorrectBasicStillWorks() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)
            .expectBody()
            .jsonPath("$.username").isEqualTo("viewer");
    }

    @Test
    void publicRouteDoesNotNeedAuthentication() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void FakeCookieCannotReplaceBasicAuthentication() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .cookie("SESSION", "fake")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void postWithBasicButNoCsrfIsForbidden() {
        client.post().uri("/api/action")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isForbidden()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED);
    }

    @Test
    void postWithBasicAndValidTestCsrfSucceeds() {
        client.mutateWith(csrf())
            .post().uri("/api/action")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted");
    }

    @Test
    void evilOriginPostStillDeniedWithCsrf() {
        client.mutateWith(csrf())
            .post().uri("/api/action")
            .header(HttpHeaders.ORIGIN, EVIL)
            .headers(h -> h.setBasicAuth(
                "viewer", "viewer-pass"))
            .exchange().expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
```

**19 HTTP tests** verify CORS filter integration, `Origin` matching, ACAO/ACAC, preflight methods/headers, Basic authentication, and CSRF. The code is designed for learners to **run themselves**; this lesson **does not claim Maven tests were executed in your workspace**. `csrf()` only exercises the security filter in memory and does not verify cross-site cookies in Chrome/Safari.

### 8.1. Separate unit tests for `CorsConfiguration`

`src/test/java/demo/cors/CorsPolicyUnitTests.java`:

```java
package demo.cors;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.web.cors.CorsConfiguration;

import static org.junit.jupiter.api.Assertions.*;

class CorsPolicyUnitTests {

    @Test
    void wildcardCannotBeCredentialed() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedOrigins(List.of("*"));
        c.setAllowCredentials(true);
        assertThrows(IllegalArgumentException.class,
            () -> c.checkOrigin("https://app.example.test"));
    }

    @Test
    void exactAllowedOriginButNotEvil() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedOrigins(List.of(
            "https://app.example.test"));
        c.setAllowCredentials(true);

        assertEquals("https://app.example.test",
            c.checkOrigin("https://app.example.test"));
        assertNull(c.checkOrigin(
            "https://evil.example.test"));
    }

    @Test
    void onlyDeclaredMethodsPass() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedMethods(List.of("GET", "POST"));
        assertNotNull(c.checkHttpMethod(HttpMethod.GET));
        assertNull(c.checkHttpMethod(HttpMethod.DELETE));
    }

    @Test
    void unlistedHeadersDoNotPass() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedHeaders(List.of(
            "Authorization", "Content-Type"));
        assertNotNull(c.checkHeaders(
            List.of("authorization")));
        assertNull(c.checkHeaders(
            List.of("X-Admin")));
    }
}
```

**Total 23 sample tests:** 19 `CorsHttpTests` and 4 `CorsPolicyUnitTests`. Unit tests invoke `CorsConfiguration.checkOrigin`/`checkHttpMethod`/`checkHeaders` without running the Security chain. Integration tests use `WebTestClient` rather than a browser. The two testing layers complement each other.

### 8.2. Running Maven

```bash
mvn test
mvn spring-boot:run
```

You can also run `mvn -Dtest=CorsHttpTests test` for only HTTP integration tests or `mvn -Dtest=CorsPolicyUnitTests test` for only policy tests. Never turn expected 403s into 200s via `permitAll()` or `allowedOrigins("*")`; fix the CORS configuration to match production requirements.

## 9. Curl recipes to verify responses

These commands target `http://localhost:8080`; `https://app.example.test` is a **simulated Origin for HTTP testing**, so no real frontend DNS is needed with curl. `curl` does not enforce CORS, so status/body only prove server behavior.

### 9.1. OPTIONS allowed origin, no Authorization

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Expect `200`, exact ACAO, ACAC `true`, ACAM containing `GET`, ACAH containing `authorization`. **Do not pass `-u` on `OPTIONS`**: browser preflights carry no Basic/Bearer credentials.

### 9.2. OPTIONS disallowed origin

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

Expect Spring's CORS processor to return `403` without ACAO. If the server unexpectedly echoes the evil origin in ACAO, check the allowlist, `@CrossOrigin`, and any gateway/proxy overwriting CORS headers.

### 9.3. OPTIONS disallowed `DELETE` method

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: DELETE' \
  -H 'Access-Control-Request-Headers: authorization'
```

Expect `403` because DELETE is not allowed. Adding `OPTIONS` to `allowedMethods` does not mean DELETE is allowed—CORS checks the `Access-Control-Request-Method` header value.

### 9.4. OPTIONS disallowed `X-Admin` header

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-admin'
```

Expect `403`. In real products, whitelist only genuinely needed custom headers; never let clients send internal admin/tenant assertions and trust those values.

### 9.5. GET allowed origin without credentials

```bash
curl -i http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test'
```

Expect `401` due to missing Basic auth, while ACAO/ACAC are present for the allowed origin. This is evidence that **CORS pass != auth pass**.

### 9.6. GET allowed origin with Basic fixture

```bash
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/me \
  -H 'Origin: https://app.example.test'
```

Expect `200` with JSON `{"username":"viewer"}`, exact ACAO, ACAC `true`, and `X-Request-Id` exposed. Use this fixture password only on localhost. In production use HTTPS and never leave real passwords/tokens in shell history.

### 9.7. GET evil origin with valid Basic

```bash
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/me \
  -H 'Origin: https://evil.example.test'
```

Expect `403` from Spring's CORS processor, with no ACAO. **CORS is not authentication**: if a non-browser client omits `Origin` and sends valid credentials, it is still processed per the API auth policy.

### 9.8. POST allowed origin without CSRF

```bash
curl -i -u viewer:viewer-pass -X POST \
  http://localhost:8080/api/action \
  -H 'Origin: https://app.example.test'
```

Expect `403` due to CSRF; a prior POST preflight can still pass. With real browsers/sessions, you need a CSRF token issuance mechanism, form/header submission matching Spring Security's repository/handler, and cookie protections. Never drop CSRF just because an Origin is allowlisted.

### 9.9. PowerShell and real accounts

PowerShell 5.1 aliases `curl` to `Invoke-WebRequest`, so use `curl.exe` when standard curl syntax is needed. Never copy Base64 Basic headers from DevTools into tickets or logs; Base64 does not encrypt secrets. Never place Bearer/session credentials into URL queries or screenshots.

## 10. How does browser QA differ from `WebTestClient`?

### 10.1. From an allowed frontend origin

Open a real HTTPS app at `https://app.example.test` and run:

```javascript
const response = await fetch("https://api.example.test/api/me", {
  method: "GET",
  credentials: "include"
});
console.log(response.status);
```

When a valid session cookie exists in a real environment, the browser can send the cookie cross-origin if `SameSite`/Secure/domain/path and browser privacy policies allow it. In the HTTP Basic demo project, `credentials:"include"` **does not log the user in on its own**; without valid Basic credentials, it receives 401. Browser DevTools Network shows the `OPTIONS` request (if triggered), the actual GET, response ACAO/ACAC, and cookie-sending decisions.

### 10.2. From a disallowed frontend origin

If the same code runs from `https://evil.example.test`, the browser blocks preflight or refuses to expose the response. For a **simple GET without preflight**, the request may still reach the server, yet JavaScript on the evil origin **cannot read** the body when ACAO forbids it. `fetch` may **reject with a `TypeError`**; JavaScript may be unable to read `response.status` on a CORS-blocked response. Thus, do **not** write browser tests expecting `response.status === 403` as if using `WebTestClient`; the two layers observe different things.

### 10.3. Checking cookies systematically

1. In DevTools Application/Storage, is the cookie stored?
2. Does the cookie have `Secure` when the API uses HTTPS; are `Domain`, `Path`, and `Expires/Max-Age` accurate?
3. Does `SameSite=Lax/Strict/None` fit the use case? Are cross-site cookies blocked/partitioned by the browser?
4. Does `fetch` specify `credentials:"include"`?
5. Did `OPTIONS` with valid Origin/ACRM/ACRH pass; does the actual response include exact ACAO and ACAC `true`?
6. If the cookie is sent yet the actual request gets 401, check session validity/authentication rather than blaming CORS.
7. If POST returns 403, check the CSRF token and authorization; never disable CSRF to "fix" it.
8. Never add `Access-Control-Allow-Origin: *` when credentialed; browsers reject wildcards with credentials.

**There is no way** to use ACAC to force Chrome/Safari to send cookies blocked by third-party cookie restrictions. If a BFF app needs cross-site sessions, examine domain/site architecture, privacy policies, CSRF, and cookie attributes—not just server headers.

## 11. Test mistakes that easily cause wrong conclusions

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Expecting `WebTestClient` GET to auto-preflight | `WebTestClient` is not a browser | Send `OPTIONS` explicitly |
| Putting `Authorization` on `OPTIONS` to "test credentials" | Standard browser preflight carries no credentials | Test anonymous `OPTIONS` pass and authenticated actual request separately |
| Asserting only `OPTIONS` status 200 | May be missing ACAO/ACAM/ACAH | Assert headers and exact allowed origin |
| Testing only allowed origins | Wildcard/reflect-all may slip through | Add negative tests for evil/null/scheme/port |
| Using `allowedOrigins("*")` with ACAC | Invalid credentialed CORS | Whitelist exact origins |
| Setting `allowedOriginPatterns("*")` to "fix" errors | May reflect every origin and leak responses | Tight patterns from a trusted registry |
| Treating `OPTIONS` 200 as an authenticated endpoint | Preflight grants no principal | Run actual 401/403/200 tests |
| Assuming no browser preflight means no CORS needed | Simple requests still need ACAO | Test actual CORS responses |
| Reading `curl` body with evil origin and thinking browsers can too | `curl` does not enforce CORS | Run separate browser DevTools/automation tests |
| Side-effecting `GET` relying on CORS against CSRF | Browsers can still send requests even if JS cannot read responses | Use safe GETs, CSRF/Origin checks, authorization |
| Using `permitAll("/api/**")` to make `OPTIONS` pass | Opens the actual API | Wire CORS filter before auth |
| Disabling CSRF because POST passed preflight | CORS is not CSRF | Keep CSRF for cookie/Basic mutations |
| Assuming ACAC `true` guarantees cookies are sent | `SameSite`, `Secure`, and third-party policies still apply | Run browser cookie tests |
| Assuming evil-Origin 403 means user lacks a role | 403 may come from the CORS processor | Distinguish filter/source |
| Trusting `Origin` as user/tenant identity | Non-browsers can forge `Origin` | Derive AuthN/AuthZ from real tokens/sessions |
| Importing Servlet `UrlBasedCorsConfigurationSource` into WebFlux | Wrong type/integration | Use the `reactive` package |
| Defining multiple overlapping `CorsWebFilter`/CORS sources | Hard-to-trace policy/duplicate headers | One clear source, tested per chain/path |
| Forgetting `Vary` when a CDN caches ACAO | Cross-origin cache poisoning | `Vary` Origin/ACRM/ACRH, private caching |
| Expecting CSRF test helper to prove browser cookies | Test helper only mocks Security context | Run E2E browser cookie flows |
| Wildcard `exposedHeaders` exposing all headers | May expose metadata/tokens to JS | Explicit `exposedHeaders` |
| API checks CORS only without auth | `curl`/non-browsers still gain access | Enforce authentication + authorization |

### 11.1. If `OPTIONS` returns 401 or 302

Check filter ordering: is `CorsConfigurationSource` integrated into Spring Security? Does the endpoint matcher cover `/api/**`? Is another `SecurityWebFilterChain` intercepting and blocking first? Is a proxy/ingress redirecting `OPTIONS` from HTTP to HTTPS or `/login`? If the app is WebFlux, make sure you did not accidentally activate the Servlet stack via `spring-boot-starter-web`.

### 11.2. If `OPTIONS` returns 403 for an allowed Origin

Check whether the request includes both `Origin` and `Access-Control-Request-Method`. Does `Access-Control-Request-Headers` contain a header **outside** `allowedHeaders`? Is the method (`DELETE`/`PUT`) in `allowedMethods`? Do scheme and port match the exact allowlist? Does the CORS configuration apply to that path (e.g., `/api/**` vs a request to `/auth/**`)?

### 11.3. If actual GET returns 200 yet the browser still reports a CORS error

Check ACAO **on the actual response**, not just `OPTIONS`; check ACAC `true` when `fetch` uses `credentials: include`, `Vary`/CDN caching, redirects, cookie policies, and the browser console. A 200 status from the HTTP server does not guarantee JavaScript can read the body.

### 11.4. If POST returns 403

If ACAO is right, the request may have passed CORS and been blocked by `CsrfWebFilter` or authorization. Check the CSRF token repository/handler: WebFlux defaults to `WebSessionServerCsrfTokenRepository` and XOR token masking in Spring Security 6.x. When using `CookieServerCsrfTokenRepository` for SPAs, implement an appropriate token flow rather than disabling CSRF or trusting `Origin` in place of tokens everywhere.

## 12. CDNs, reverse proxies, and multiple origins

**Origin responses can vary by request `Origin`**. When a server whitelists multiple frontends, `Access-Control-Allow-Origin` must match the allowed origin. Thus `Vary: Origin` (and when needed `Access-Control-Request-Method`/`Access-Control-Request-Headers`) is vital so caches/CDNs do not serve Origin A's ACAO to Origin B.

For private responses, manage `Cache-Control` and cache keys by identity/authorization, or disable shared caching. Never let User A's JSON response land in a shared CDN by mistaking CORS for auth. Reverse proxies can also overwrite CORS headers or handle `OPTIONS` themselves; in-memory integration tests do not prove production ingress/CDNs, so test in staging over real URLs.

### 12.1. Proxy forwarded headers and scheme

`Forwarded`, `X-Forwarded-Proto`, and `X-Forwarded-Host` can make the server perceive a different request origin/target than the external Internet URL if a reverse proxy is misconfigured. Trust forwarded headers only from trusted proxies that strip/rewrite them. Otherwise, attackers can spoof headers and corrupt origin comparisons, redirect URIs, or logs.

### 12.2. Tenant-specific frontend origins

If tenants have frontends `https://acme.portal.example` and `https://globex.portal.example`, issuing per-tenant CORS requires checking domain ownership in a trusted tenant registry alongside backend auth. Never use a dynamic echo-all `Origin` to "avoid maintaining a list". Even when a browser lets Tenant A call the API, the backend must still check token `tenant_id` and resource permissions: CORS policy governs **cross-origin response reading**, not tenant authorization.

## 13. Pre-production review checklist

1. Specify frontend origins precisely as `scheme://host:port`, not domain substrings.
2. Document the origin/method/header/credentials matrix per path.
3. Integrate CORS before Spring Security WebFlux authentication; test preflight **without Cookie/Authorization**.
4. Use `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` or properly ordered reactive `CorsWebFilter`; avoid Servlet imports.
5. With `allowCredentials(true)`, whitelist exact origins or tight patterns only—never ACAO wildcard.
6. Test allowed/evil/null/scheme/port, disallowed `DELETE` method, disallowed `x-admin` header, and preflight `maxAge`/`Vary`.
7. Test actual GET anonymous 401 and authenticated 200, invalid credentials 401, and missing-Origin non-browser requests.
8. Test POST with valid Basic/session but missing CSRF -> 403, succeeding only with an appropriate CSRF token.
9. Never change an `authenticated()` API to `permitAll()` just to make CORS tests pass.
10. Test browser enforcement separately: a CORS-blocked `fetch` must not expose the response object to JS.
11. Verify cookie `SameSite`/`Secure`/`HttpOnly`/domain/path and third-party policies on target browsers.
12. Never use `Origin` as user/tenant authentication; verify scopes/roles/ownership on the backend.
13. Verify `Vary`, CDN/authenticated response caching, and reverse-proxy `OPTIONS`/redirects.
14. Never log `Authorization` headers, sessions, or CSRF tokens in test artifacts, tracing, or screenshots.
15. When upgrading Spring Security/Spring Framework/ingress, re-run CORS HTTP and browser regression tests.

## 14. Self-assessment questions

**1.** Which headers does a preflight need?  
`OPTIONS` with `Origin` and `Access-Control-Request-Method`; `Access-Control-Request-Headers` may list intended header names.

**2.** Does a preflight send user cookies or Bearer credentials?  
Under standard browser CORS, **no**. That is why CORS must run before authentication.

**3.** Preflight returns 200 yet GET returns 401—is CORS misconfigured?  
No. The origin was allowed, while the actual request lacked valid credentials.

**4.** Can ACAO `*` and ACAC `true` be used together for credentialed browser fetch?  
No. An explicit origin is required.

**5.** Does `credentials:"include"` guarantee cross-site session cookies are sent?  
No; `SameSite`, `Secure`, domain, and third-party policies still apply.

**6.** Why must `WebTestClient` send `OPTIONS` explicitly?  
Because `WebTestClient` does not automatically execute browser preflight logic.

**7.** Does CORS replace CSRF for cookie-authenticated POSTs?  
No. Browsers can still send requests even when JavaScript cannot read responses, so CSRF/Origin/authorization protections remain necessary.

**8.** Why are HTTP and HTTPS on the same host different origins?  
An origin includes scheme, host, and port—not just the domain.

**9.** Can an HTTP client without `Origin` call the API?  
Yes, if authentication/authorization allow it; CORS is not a firewall.

**10.** Why doesn't testing an evil `Origin` with `curl` prove browsers will block it?  
`curl` does not enforce CORS; actual browser enforcement must be checked.

**11.** If an actual POST returns 403, what must be checked?  
Distinguish the CORS processor, CSRF token, authorization rules, and security filter ordering.

**12.** Does `Access-Control-Expose-Headers` let JavaScript read `Set-Cookie`?  
No. `Set-Cookie` is managed by the browser, not an arbitrary response header readable by JS.

**13.** Why is `Vary: Origin` needed?  
So caches do not serve Origin A's ACAO to Origin B, preventing cross-origin cache poisoning.

**14.** Does putting a broad `@CrossOrigin` on a controller keep Spring Security policy consistent?  
Not reliably; overlapping configs can yield unpredictable behavior. Use one clear source and test every chain/path.

**15.** Does test `csrf()` prove production `SameSite` cookie behavior?  
No. It is a request test mutator; browser cookie flows require E2E tests.

### Official references

- Spring Security – Reactive CORS: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html
- Spring Framework – CORS WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Security – Testing Reactive Web Security: https://docs.spring.io/spring-security/reference/reactive/test/web/
- Spring Security – Testing with CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security – CSRF WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Framework API – CorsConfiguration: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- MDN – CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN – Credentials + ACAO wildcard error: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials
- Fetch Standard – CORS: https://fetch.spec.whatwg.org/

**Summary:** Testing preflight, disallowed origins, and credentials in WebFlux requires separating **unauthenticated** `OPTIONS` from actual GET/POST requests **with or without auth**, checking exact ACAO/ACAC/ACAM/ACAH headers, and keeping CSRF/authorization distinct. `WebTestClient`/`curl` verify server responses; browser tests verify whether JavaScript can actually read responses and whether cookies are sent.