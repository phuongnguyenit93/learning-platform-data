# Ordering of CORS, Preflight, and Security Filters in Spring WebFlux

In a **Spring WebFlux** application with Spring Security, requests from a frontend on a different origin must pass through two independent mechanisms: **CORS** (Cross-Origin Resource Sharing) and **authentication/authorization**. If CORS is processed too late, the browser may send a valid **preflight** request, only for the server to demand login before checking CORS. The typical consequence is `401 Unauthorized` or `403 Forbidden` on `OPTIONS`, even when the actual GET/POST request carries a valid token.

**Most important rule:** CORS must have the chance to handle preflight **before** authentication and authorization. Spring Security WebFlux supports this via CORS integration inside `SecurityWebFilterChain` or via a `CorsWebFilter` registered outside and running before security. Do not simply add `OPTIONS /** permitAll` and treat CORS as configured.

This lesson covers the browser → preflight → WebFilter/Security → controller flow; ordering filters in the reactive stack; configuring origin/method/header/credentials safely; distinguishing CORS from CSRF; and a Java 17 application with WebTestClient integration tests.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish same-origin policy, CORS, and authentication.
2. Recognize preflight requests by `OPTIONS`, `Origin`, and `Access-Control-Request-Method`.
3. Explain why preflight must not be blocked by authentication before CORS runs.
4. Distinguish preflight from actual CORS requests and ordinary `OPTIONS` requests.
5. Understand the flow across `WebFilter`, Spring Security `WebFilterChainProxy`, and `HandlerMapping` in WebFlux.
6. Configure `ServerHttpSecurity.cors(...)` with a reactive `CorsConfigurationSource`.
7. Configure a standalone `CorsWebFilter` and specify ordering with `@Order` when choosing that approach.
8. Distinguish `SecurityWebFiltersOrder` inside the security chain from outer `WebFilter` ordering.
9. Choose `allowedOrigins`, `allowedMethods`, `allowedHeaders`, `allowCredentials`, and `maxAge`.
10. Understand why `@CrossOrigin` or `WebFluxConfigurer.addCorsMappings` may be insufficient if Security blocks preflight early.
11. Avoid configuration errors with multiple `SecurityWebFilterChain` beans or multiple CORS processors.
12. Test valid preflight, denied origins, denied headers/methods, and actual requests with/without credentials.
13. Distinguish CORS from CSRF; never disable CSRF just to fix a preflight error.

## 2. Origin, Same-Origin Policy, and CORS

An **origin** consists of three parts: scheme, host, and port. The following two addresses have different origins even though they share a parent domain:

~~~text
https://app.example.test
https://api.example.test
~~~

These two addresses also have different origins because their ports differ:

~~~text
http://localhost:3000
http://localhost:8080
~~~

Browsers enforce the same-origin policy on many JavaScript operations. When a frontend at `https://app.example.test` calls an API at `https://api.example.test`, the browser needs a CORS policy from the API to know whether the frontend is permitted to read the response.

CORS is expressed through HTTP headers, for example:

~~~http
Origin: https://app.example.test
Access-Control-Allow-Origin: https://app.example.test
~~~

The `Origin` header is sent by the browser to tell the server where the request originates. The `Access-Control-Allow-Origin` header is returned by the server so the browser can decide whether JavaScript may access the response.

### 2.1. CORS Does Not Authenticate Users

CORS does not identify who the user is. An allowed origin does not mean the request is allowed to read sensitive data without a valid token or cookie.

- **CORS:** which origin's web app is allowed to call and read responses in the browser?
- **Authentication:** who is calling?
- **Authorization:** does that caller have permission to access the specific resource?
- **CSRF:** is a state-changing action being triggered unintentionally using ambient browser credentials?

The server must still verify authentication and authorization on the actual request. Clients like `curl`, Postman, or backend services are not bound by the browser's same-origin policy. Therefore, **never use CORS as a mechanism to protect APIs from non-browser clients**.

### 2.2. CORS Is Also Not a Reverse Proxy Allowlist

An allowlisted origin allowing browsers to read responses is different from an IP/network allowlist. A non-browser client can set any `Origin` header or omit `Origin` entirely. API authorization must rely on principals, scopes, roles, policies, mTLS, or other trustworthy mechanisms.

## 3. What Is Preflight?

Browsers send a **preflight** to ask the server before sending the actual request in certain cases: using an HTTP method outside the safelisted methods, sending a non-CORS-safelisted request header (such as `Authorization`), or using a `Content-Type` outside the simple CORS-safelisted types.

For example, a frontend at `https://app.example.test` wants to send a GET with an `Authorization` header:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/items",
  {
    method: "GET",
    headers: { Authorization: "Bearer token-from-auth-flow" },
    credentials: "include"
  }
);
~~~

The browser may first send:

~~~http
OPTIONS /api/items HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

**Preflight requests usually do not carry cookies or `Authorization` credentials.** `Access-Control-Request-Headers: authorization` only declares that the actual request intends to send the `Authorization` header; the preflight itself does not supply the bearer token.

If valid, the server responds, for example:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
~~~

Only then does the browser send the actual GET with credentials per the fetch configuration. Note that the status code may be 200 or 204 depending on the server/framework; what matters is a success status and the proper CORS response headers.

### 3.1. Conditions for Recognizing a Preflight

A standard CORS preflight contains:

1. HTTP method `OPTIONS`.
2. `Origin` header.
3. `Access-Control-Request-Method` header containing the actual request's HTTP method.

`Access-Control-Request-Headers` may or may not be present, depending on which headers the actual request intends to send.

**Not every `OPTIONS` request is a CORS preflight.** An `OPTIONS /api/items` request without `Origin` and `Access-Control-Request-Method` must not be treated as a preflight simply because its method is `OPTIONS`.

### 3.2. CORS Simple Requests and Actual Requests

Some simple requests may skip preflight, yet still carry `Origin`. The server must still return proper CORS headers on the actual response if browsers are to read it.

Example:

~~~http
GET /api/public-data HTTP/1.1
Origin: https://app.example.test
~~~

A successful response without `Access-Control-Allow-Origin` can still be blocked from JavaScript access by the browser, even though the actual HTTP status is 200.

### 3.3. Preflight Cache

`Access-Control-Max-Age` tells the browser how long it may cache the preflight result up to browser-imposed limits. This does not cache the actual API response, nor does it bypass authentication/authorization on subsequent actual requests.

## 4. Why Ordering CORS Before Spring Security Matters

Suppose `/api/items` requires authentication for every request:

~~~text
Browser                    WebFlux Server

OPTIONS /api/items
Origin: app.example.test
AC-Request-Method: GET
(no Authorization)   -------->
                              Security checks first
                              => anonymous user
                      <-------- 401 Unauthorized

Browser stops; actual GET is not sent
~~~

Even an actual request with a valid token cannot rescue this scenario because the browser stops after the failed preflight.

Correct flow:

~~~text
Browser                    WebFlux Server

OPTIONS + Origin +
Access-Control-Request-Method
(no credentials)    -------->
                              CORS checks origin/method/headers
                              => valid
                      <-------- 200 + Access-Control-Allow-*

GET /api/items
Authorization: ...  -------->
                              CORS checks actual request
                              Authentication verifies credentials
                              Authorization checks permissions
                              Handler/controller
                      <-------- 200 + data + CORS headers
~~~

For an invalid preflight, the CORS processor must reject it, typically with `403 Invalid CORS request`. There is no reason to forward an invalid preflight to a business controller.

### 4.1. What Does "Before Security" Mean Precisely?

It does not strictly require a `WebFilter` bean completely outside Spring Security. There are two valid approaches:

- **CORS inside `SecurityWebFilterChain`:** call `http.cors(cors -> cors.configurationSource(source))`; Spring Security places the CORS processor at the CORS stage inside the internal chain before authentication/authorization.
- **Standalone `CorsWebFilter`:** create a `WebFilter` that runs early enough before Spring Security's `WebFilterChainProxy`; preflights can be handled and completed before reaching Security.

The key is that the CORS processor **executes before steps that can reject anonymous requests**, not simply having an annotation or a bean named "cors".

## 5. Filter and Handler Layers in WebFlux

WebFlux processes requests through a `WebFilter` chain, then `WebHandler`/`DispatcherHandler`, followed by `HandlerMapping` and controllers.

Reactive Spring Security integrates via `WebFilterChainProxy`, which contains `SecurityWebFilterChain` instances and security filters.

~~~text
HTTP server
   |
   v
WebFilter chain (ordered by @Order / Ordered)
   |
   +--> Standalone CorsWebFilter (if used)
   |
   +--> Spring Security WebFilterChainProxy
   |       |
   |       +--> select SecurityWebFilterChain
   |       |
   |       +--> internal CORS (if configured)
   |       +--> Authentication
   |       +--> Authorization
   |       +--> other security filters
   |
   +--> Remaining business WebFilters
   |
   v
DispatcherHandler
   |
   v
HandlerMapping / controller / functional endpoint
~~~

This diagram is conceptual: exact ordering depends on configured beans and security chains. Do not assume a custom `WebFilter` runs before or after all of security without checking its `@Order`.

### 5.1. Ordering Standalone `WebFilter`s

When declaring a `WebFilter` as a Spring bean, use `@Order` on the bean or implement `Ordered` to set precedence. Smaller order values run earlier. For an independent `CorsWebFilter`, `Ordered.HIGHEST_PRECEDENCE` can be used to ensure it runs very early.

### 5.2. `SecurityWebFiltersOrder` Is a Different Order

`SecurityWebFiltersOrder` governs the relative positions of filters **inside** a Spring Security chain, such as CORS, authentication, or authorization. It does not replace `@Order` for outer `WebFilter` beans outside security.

For instance, when a custom authentication filter is needed inside a security chain, Spring Security provides `addFilterAt` or `addFilterBefore`/`addFilterAfter` using `SecurityWebFiltersOrder`. For CORS, prefer `http.cors(...)` rather than guessing a position for a custom filter.

### 5.3. `HandlerMapping` CORS Can Run Too Late

Spring WebFlux supports CORS at `HandlerMapping` via `@CrossOrigin` and `WebFluxConfigurer.addCorsMappings`. When Spring Security is not blocking upfront, these can work fine.

However, if Security rejects anonymous `OPTIONS` in the `WebFilter` chain, the request **never reaches `HandlerMapping`**. Therefore, controller-level CORS configuration is not enough to fix security ordering. With Spring Security WebFlux, configure CORS integration before authentication/authorization.

## 6. Recommended Approach: CORS Inside `SecurityWebFilterChain`

For a WebFlux API protected by Spring Security, a clean approach is creating a reactive `UrlBasedCorsConfigurationSource` and passing it to `ServerHttpSecurity.cors`.

~~~java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.test")
    );
    config.setAllowedMethods(List.of("GET"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Trace-Id")
    );
    config.setAllowCredentials(true);
    config.setMaxAge(1800L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", config);
    return source;
}

@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        UrlBasedCorsConfigurationSource corsConfigurationSource) {

    return http
        .cors(cors ->
            cors.configurationSource(corsConfigurationSource)
        )
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is the core configuration; the complete example application later includes imports, controllers, and the user store.

**Why does this work?**

- The source supplies CORS policy for `/api/**` URLs.
- Security places the CORS processor at the right spot in the chain.
- Valid preflights are handled without requiring credentials.
- Actual requests continue through authentication/authorization.
- Disallowed origins, HTTP methods, or request headers are rejected by the CORS processor.

### 6.1. Import the Right Reactive Package

WebFlux CORS uses:

~~~java
org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource
org.springframework.web.cors.reactive.CorsConfigurationSource
org.springframework.web.cors.reactive.CorsWebFilter
~~~

Do not mistakenly import `org.springframework.web.cors.UrlBasedCorsConfigurationSource` or the servlet `CorsFilter`. Those belong to Servlet/Spring MVC, not reactive WebFlux.

`CorsConfiguration` (the policy object) uses the shared package:

~~~java
org.springframework.web.cors.CorsConfiguration
~~~

### 6.2. Is `permitAll` on `OPTIONS` Necessary?

In the configuration above, it is not required to add:

~~~java
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

Valid preflights are handled by the CORS integration before authorization. If the application has real non-CORS-preflight `OPTIONS` endpoints, those endpoints should still follow appropriate authorization policies.

Permitting all `OPTIONS` only partially addresses authorization; it **does not generate** `Access-Control-Allow-*` headers and does not validate origin/method/headers. Thus `permitAll OPTIONS` does not replace a CORS processor.

## 7. Alternative Approach: `CorsWebFilter` Running Before Security

Another valid approach is registering `CorsWebFilter` at the standalone `WebFilter` layer.

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
CorsWebFilter corsWebFilter(
        UrlBasedCorsConfigurationSource corsSource) {

    return new CorsWebFilter(corsSource);
}
~~~

This handles preflights early outside the security filter chain. However, **choose one primary CORS management mechanism** for the same URL scope:

- If using `http.cors(...configurationSource...)`, do not also add a standalone `CorsWebFilter` without a clear reason.
- If using a standalone `CorsWebFilter`, avoid simultaneously creating a second CORS processor in Spring Security or `HandlerMapping` with a different policy.
- If different paths need different policies, express them in the same source or design chains explicitly.

**Do not mechanically combine both approaches in one application.** Two CORS processors handling the same request can emit duplicate headers, conflicting policies, or confusing debugging behavior.

### 7.1. When to Use an Outer `CorsWebFilter`?

It can be helpful when you want CORS to apply uniformly across multiple `SecurityWebFilterChain` instances or multiple WebFlux handler styles (annotated/functional) with centralized policy before Security.

### 7.2. When to Use `http.cors`?

Suitable when you want CORS to be an explicit part of Security configuration, especially in APIs with few security chains. Whichever option you choose, test actual preflight over HTTP rather than merely checking that a bean was created.

## 8. Configuring `CorsConfiguration` Safely

Key properties:

| Property | Role | Example |
| --- | --- | --- |
| `allowedOrigins` | Exact allowed origins | `https://app.example.test` |
| `allowedOriginPatterns` | Controlled origin patterns | `https://*.example.test` |
| `allowedMethods` | Allowed **actual** HTTP methods | `GET`, `POST` |
| `allowedHeaders` | Request headers clients may send | `Authorization`, `Content-Type` |
| `exposedHeaders` | Non-safelisted response headers JS may read | `X-Request-Id` |
| `allowCredentials` | Allow credentialed CORS requests | `true`/`false` |
| `maxAge` | Preflight cache duration (seconds) | `1800` |

### 8.1. `allowedMethods` Does Not Strictly Need `OPTIONS`

Preflight uses the `OPTIONS` method, but `Access-Control-Request-Method: GET` asks permission for the **actual GET**. Thus if an endpoint only supports GET, `allowedMethods(List.of("GET"))` suffices to handle GET preflights. Only add `OPTIONS` if the application genuinely wants to support `OPTIONS` as a requested method, not because preflight uses `OPTIONS`.

### 8.2. Allowed Headers vs. Exposed Headers

`allowedHeaders` controls **request** headers the browser is allowed to send, such as `Authorization` and `X-Trace-Id`.

`exposedHeaders` allows JavaScript to read additional **response** headers outside the CORS-safelisted response headers, such as `X-Request-Id`.

Setting `exposedHeaders("Authorization")` does not let the browser send `Authorization`. You need `allowedHeaders("Authorization")`.

### 8.3. `allowCredentials=true` and Wildcards

When allowing credentials, do not set `allowedOrigins("*")`. Spring rejects combining a wildcard origin with `allowCredentials(true)` because the response must name the valid origin explicitly.

Use an exact allowlist:

~~~java
config.setAllowedOrigins(
    List.of("https://app.example.test")
);
config.setAllowCredentials(true);
~~~

If dynamic origins are genuinely needed, `allowedOriginPatterns` can reflect the matched origin, but the pattern must be sufficiently narrow. Never use `https://*` or overly broad patterns for APIs using cookies/sessions/tokens.

### 8.4. Be Careful with `localhost` in Development

Origin includes the port. If the frontend is at `localhost:5173`, that is a different origin from `localhost:3000`. Create a separate profile for dev:

~~~java
config.setAllowedOrigins(
    List.of(
        "http://localhost:5173",
        "https://app.example.test"
    )
);
~~~

Do not carry unnecessary `localhost` origins into production policies. Do not confuse the API server hostname with the frontend origin.

### 8.5. `Vary` and Caching

A response that varies by `Origin` requires caches to distinguish origins. Spring's CORS processor normally adds `Vary` for `Origin` and relevant preflight request headers. When using a reverse proxy/CDN, preserve `Vary` headers and never cache a response containing `Access-Control-Allow-Origin` for origin A and serve it to origin B.

## 9. CORS, Basic Auth, Bearer Tokens, and Cookies

Preflights usually do not carry credentials; actual requests may carry:

- Session cookies when the browser is configured and cookie policies permit.
- `Authorization`: Basic or Bearer.
- Other authentication mechanisms depending on browser/network.

In the demo, the actual GET uses HTTP Basic authentication; the preflight only asks whether the allowlisted origin may send the `Authorization` header.

### 9.1. Do Not Enable `credentials=true` for Every API

If the frontend only sends cross-origin requests without cookies or credentials requiring CORS credentials mode, `allowCredentials(true)` may not be needed. Match how the frontend actually calls `fetch`/XHR.

With `fetch(..., {credentials: "include"})`, the response requires `Access-Control-Allow-Credentials: true` and an explicit origin, not `*`.

### 9.2. Preflight Is Not Where JWTs Are Verified

Do not require a JWT on preflight. The browser sends `Access-Control-Request-Headers: authorization`, not the actual request's bearer token in the preflight `Authorization` header. The token is verified when the actual request reaches the Security filter chain.

### 9.3. Successful Authentication Does Not Guarantee CORS Success

A GET request with a valid token from a non-allowlisted origin will still be blocked by the browser from reading the response, or rejected by the server's `CorsWebFilter`. Conversely, an allowlisted origin does not let a GET without a token enter the controller.

## 10. CORS vs. CSRF

**CORS** controls cross-origin JavaScript response reading and certain browser preflight flows. **CSRF** prevents browsers from automatically sending credentials like session cookies to perform unintended state-changing actions.

They are related but do not replace one another.

### 10.1. `OPTIONS` Preflight and CSRF

Preflight uses `OPTIONS`, which belongs to the group of HTTP methods generally considered safe. By default, Spring Security CSRF protection targets state-changing methods such as `POST`/`PUT`/`PATCH`/`DELETE` and does not block `OPTIONS` preflights for lacking a CSRF token.

If a preflight gets 401/403, first inspect CORS configuration, authentication/authorization, origin, requested method/headers, and filter order. Never disable CSRF by default to cure a CORS error.

### 10.2. Actual `POST` Still Needs Appropriate Protection

Suppose a `POST` preflight succeeds. If the browser sends the actual `POST` with a session cookie and no CSRF token, Spring Security can still return 403. That is a separate protection layer and may be the intended behavior.

An API using bearer tokens in the `Authorization` header, not relying on ambient credentials, can evaluate CSRF differently from a cookie-based session app. Any decision to disable CSRF must be grounded in the threat model and authentication mechanism, not on the fact that the frontend runs on a different origin.

### 10.3. Do Not Disable All Security to Test CORS

Avoid dangerous workarounds:

~~~java
// Not the right approach:
.authorizeExchange(a -> a.anyExchange().permitAll())
.csrf(csrf -> csrf.disable())
~~~

They alter the entire application's security policy without guaranteeing CORS is actually handled properly.

## 11. Multiple `SecurityWebFilterChain`s and `@Order`

Spring Security WebFlux can choose among multiple `SecurityWebFilterChain` beans using `securityMatcher` and `@Order`.

Example route groups:

~~~text
/api/**   -> API security chain
/admin/** -> Admin security chain
/**       -> fallback chain
~~~

Chains with lower order values are evaluated first. A request enters the first matching chain; other chains are not merged into a combined filter set.

### 11.1. Common Multi-Chain Pitfall

If CORS is configured only in the `/api/**` chain while a preflight targets `/admin/**`, the `/admin/**` chain may reject the request before the desired CORS processor runs.

If `securityMatcher` rules depend on the HTTP method, remember that preflight uses **`OPTIONS`** while the actual request uses `GET`/`POST`. A matcher selecting only `GET` may miss `OPTIONS`, routing the preflight into a different fallback chain.

### 11.2. Design Guidelines

- Use a consistent CORS source for paths requiring cross-origin access.
- If CORS is configured inside individual Security chains, ensure preflights match the right chain as well.
- Consider a global `CorsWebFilter` running before all security chains if it fits the architecture.
- Avoid registering multiple CORS beans with conflicting policies.
- Test each real path with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.

### 11.3. Rule Order Inside `authorizeExchange`

Even within a single chain, rule order matters:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
~~~

Specific rules come before broad rules. However, these rules handle authorization, not CORS. If the CORS processor handles preflight before authorization, valid `OPTIONS` requests do not need a `permitAll` rule.

## 12. Complete Java 17, Spring Boot, and `WebTestClient` Example

The example uses Java 17 and **Spring Boot 3.5.16** (available on Maven Central). This is a pinned baseline for reproducibility; in production, use a supported version with appropriate security patches.

The application exposes an authenticated `GET /api/items` endpoint. Only frontend `https://app.example.test` is allowed to send CORS GET requests with `Authorization`/`X-Trace-Id` headers. Valid preflights must be processed before authentication, while actual GET requests without credentials still receive 401.

### 12.1. Project Structure

~~~text
webflux-cors-security/
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/CorsSecurityApplication.java
    └── test/
        └── java/demo/CorsSecurityApplicationTest.java
~~~

### 12.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 12.3. `CorsSecurityApplication.java`

~~~java
package demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class CorsSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsSecurityApplication.class, args);
    }
}

record ItemView(String code, String label) {}

@RestController
@RequestMapping("/api")
class ItemController {

    @GetMapping("/items")
    Mono<List<ItemView>> getItems() {
        return Mono.just(List.of(
            new ItemView("ITEM-1", "visible after authentication")
        ));
    }
}

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(
            List.of(
                "Authorization",
                "Content-Type",
                "X-Trace-Id"
            )
        );
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {

        return http
            .cors(cors ->
                cors.configurationSource(corsConfigurationSource)
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {

        UserDetails reader = User.withUsername("reader")
            .password(passwordEncoder.encode("read-pass"))
            .roles("READER")
            .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
~~~

**Highlights of the example:**

1. CORS policy applies to `/api/**`.
2. Only `https://app.example.test` is allowed.
3. `allowedMethods(GET)` still permits `OPTIONS` preflight asking for GET access.
4. `allowedHeaders` lets actual requests send `Authorization`, `Content-Type`, and `X-Trace-Id`.
5. `allowCredentials(true)` returns the header enabling credentialed requests from the allowed origin.
6. `http.cors(...)` places the CORS processor at the right position in the security chain.
7. `/api/**` still requires authentication.
8. HTTP Basic here is a demo mechanism; the user/password uses BCrypt.
9. Configuration does not disable CSRF; GET does not require a CSRF token.
10. `OPTIONS /** permitAll` is not needed.

**Production note:** Never use hardcoded users/passwords; replace with an identity provider, secret manager, or proper user store. Never use HTTP Basic over unencrypted connections; deploy APIs over HTTPS/TLS. CORS is only a browser control layer, not a substitute for authentication/authorization.

### 12.4. `CorsSecurityApplicationTest.java`

Tests use a real HTTP server on a random port to traverse both the CORS filter and security chain.

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CorsSecurityApplicationTest {

    private static final String ALLOWED =
        "https://app.example.test";

    private static final String DENIED =
        "https://evil.example.test";

    @Autowired
    WebTestClient client;

    @Test
    void preflightIsAcceptedWithoutAuthentication() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,x-trace-id"
            )
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED
            )
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"
            );
    }

    @Test
    void actualGetWithoutAuthenticationRemainsProtected() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED
            );
    }

    @Test
    void authenticatedGetFromAllowedOriginSucceeds() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(headers ->
                headers.setBasicAuth("reader", "read-pass")
            )
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ALLOWED
            )
            .expectBody()
            .jsonPath("$[0].code").isEqualTo("ITEM-1");
    }

    @Test
    void preflightFromOtherOriginIsRejected() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, DENIED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightWithForbiddenMethodIsRejected() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightWithForbiddenHeaderIsRejected() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "x-admin-secret"
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void actualGetFromDeniedOriginIsRejected() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, DENIED)
            .headers(headers ->
                headers.setBasicAuth("reader", "read-pass")
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void ordinaryOptionsIsNotCorsPreflight() {
        client.options()
            .uri("/api/items")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void sameOriginStyleRequestStillRequiresAuthentication() {
        client.get()
            .uri("/api/items")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

**Meaning of each test group:**

- Valid preflight **needs no Authorization/cookie** and receives CORS headers.
- Actual GET from an allowed origin without authentication still returns 401.
- Actual GET with valid HTTP Basic returns 200 and JSON.
- An origin outside the allowlist returns 403 even with Basic credentials.
- Preflight requesting `POST` is rejected because policy only allows `GET`.
- Preflight requesting `X-Admin-Secret` is rejected because that header is not allowlisted.
- `OPTIONS` without preflight headers still goes through security rules.
- GET without `Origin` is not implicitly permitted because Security remains in effect.

The tests verify actual HTTP behavior. They do not assume browsers send tokens on preflight, nor do they claim a CORS header replaces user authorization.

### 12.5. Running Build and Tests

If the project already has a Gradle wrapper:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

If there is no wrapper yet but a compatible Gradle 8.x is installed, run:

~~~bash
gradle test
~~~

Run the application:

~~~bash
gradle bootRun
~~~

Tests use a random port; there is no need to start a separate server before running tests.

### 12.6. Manual Testing with `curl`

Start the application on `localhost:8080`. Send a preflight:

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
~~~

Expected result: success response with `Access-Control-Allow-Origin` for the allowed origin; this request **does not need** `Authorization`.

Send an actual request with credentials:

~~~bash
curl -i -u reader:read-pass \
  -H "Origin: https://app.example.test" \
  http://localhost:8080/api/items
~~~

Expected result: HTTP 200 and JSON containing an element with `code=ITEM-1`. This directly tests the API with `curl`; `curl` displays headers/body but does not enforce CORS like a browser.

Send an actual request without credentials:

~~~bash
curl -i \
  -H "Origin: https://app.example.test" \
  http://localhost:8080/api/items
~~~

Expected result: HTTP 401, even though the origin is valid. This demonstrates that CORS does not replace Security.

## 13. JavaScript Frontend and Credentials Configuration

Example frontend calling an API with a Bearer token:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/items",
  {
    method: "GET",
    headers: {
      Authorization: "Bearer " + accessToken,
      "X-Trace-Id": traceId
    },
    credentials: "include"
  }
);

if (!response.ok) {
  throw new Error("HTTP status: " + response.status);
}

const items = await response.json();
~~~

This is a frontend illustration and does not run directly against a demo server configured only for HTTP Basic. To use Bearer tokens, the backend needs OAuth2 Resource Server/JWT authentication or an equivalent token mechanism. The CORS policy only allows the browser to send these headers and read the response; it does not recognize tokens itself.

### 13.1. Credentials Mode

`credentials: "include"` tells the browser to send relevant credentials per cookie policy/authentication mechanism and requires `Access-Control-Allow-Credentials: true` from a specific origin in the response. If an API needs neither cookies nor credentialed mode, `allowCredentials(false)` may be more appropriate.

### 13.2. Never Put Tokens in URLs

Never pass a bearer token in the query string merely to avoid the `Authorization` header or preflight. Query strings can be logged in proxies, analytics, and browser history. Preflight is normal behavior; configure the server properly rather than trying to bypass it.

## 14. Debugging 401/403 Preflights Step by Step

When the frontend reports a CORS error, do not apply random fixes. Follow this process:

### 14.1. Inspect Actual Requests in DevTools

Open the Network tab and check:

- What status did the `OPTIONS` preflight receive?
- Were `Origin` and `Access-Control-Request-Method` present?
- Which request headers did the browser ask for?
- Was `Access-Control-Allow-Origin` present in the response?
- Was the actual GET/POST sent after the preflight?
- Did the actual request return 401/403/500, or did the browser simply block reading the response?

Do not rely solely on a "CORS error" line in the console; browsers sometimes hide response details from JavaScript when CORS fails.

### 14.2. Preflight Returns 401

Common cause: security demanded authentication before CORS ran.

Check:
1. Is `http.cors(...)` or an early `CorsWebFilter` configured?
2. Is the reactive `CorsConfigurationSource` imported from the right package?
3. Does the path match the registered CORS mapping?
4. Do multiple security chains route the preflight into a different chain?
5. Is a custom `WebFilter` checking tokens on every request, including `OPTIONS`, before CORS?

### 14.3. Preflight Returns 403

This may be an intentional rejection by the CORS policy rather than an authentication error.

Check:
- Does `Origin` match scheme/host/port exactly?
- Is `Access-Control-Request-Method` in `allowedMethods`?
- Does `Access-Control-Request-Headers` contain a header missing from `allowedHeaders`?
- Was `allowCredentials=true` configured alongside `allowedOrigins="*"`?
- Is a second CORS processor enforcing a conflicting policy?

### 14.4. Preflight Is 200, Actual Request Is 401

CORS is likely fine. Check the token/cookie, `Authorization` formatting, expired credentials, authentication provider, and whether a proxy forwards `Authorization`. Do not try to fix this by loosening `allowedOrigins`.

### 14.5. Preflight Is 200, Actual Request Is 403

This could be authorization (missing role/scope), CSRF on a state-changing request, or an actual CORS policy mismatching preflight. Distinguish via server/security logs, status, response headers, and request type.

### 14.6. No Preflight Occurs

Not every request triggers a preflight. A simple GET may send only the actual request. If the actual response lacks CORS headers, the browser can still block reading the body. Do not conclude CORS is irrelevant just because "no `OPTIONS` appeared".

### 14.7. Proxy or Gateway Blocks `OPTIONS`

Correct Spring configuration is futile if a gateway returns 401/403 before the request reaches the application.

Check:
- API gateway/WAF rules.
- Nginx/Ingress method allowlists.
- Whether CORS is applied twice at both CDN and backend.
- Whether reverse proxies preserve `Origin` and `Access-Control-Request-*`.
- Whether `OPTIONS` even reaches the Spring service.

If the gateway handles CORS on behalf of the backend, the gateway policy must be consistent and must not weaken protection on actual requests.

## 15. Observing Filter Order and Safe Logging

### 15.1. Logs Distinguishing Preflight from Actual Requests

In development environments, you can log method, path, and header presence (never log tokens):

~~~text
OPTIONS /api/items
Origin=https://app.example.test
Access-Control-Request-Method=GET
Access-Control-Request-Headers=authorization
authorization-present=false

GET /api/items
Origin=https://app.example.test
authorization-present=true
~~~

Never log raw `Authorization` or cookie values. A custom filter running **after** the CORS processor may not see preflights that CORS has already handled and completed. If preflight metrics are needed, place observation hooks before CORS or log at the gateway/network layer.

### 15.2. Custom `WebFilter` Ordering

For custom `WebFilter` beans, `@Order` controls placement in the outer `WebFilter` chain. For security-internal filters, use `ServerHttpSecurity` APIs and `SecurityWebFiltersOrder`.

Do not add a custom filter requiring `Authorization` on all requests at `Ordered.HIGHEST_PRECEDENCE` and expect `http.cors(...)` (inside Security) to still handle preflight before that filter. If such a filter exists, either move authentication into the Security chain or let CORS run ahead of the custom filter.

### 15.3. Metrics to Monitor

- Preflight count and 2xx/4xx rates.
- Preflight processing latency.
- CORS rejections grouped by reason (origin/method/header), avoiding high-cardinality tags.
- Actual 401/403 counts by route and auth mechanism.
- Frequency of browser CORS errors after deployments.
- Proxy/gateway telemetry for blocked `OPTIONS`.

Never use arbitrary client-supplied `Origin` values as unbounded metric tags, as cardinality can grow rapidly.

## 16. Common Configuration Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Letting authentication run before CORS | Credential-less preflight receives 401 | Integrate CORS before authentication |
| Adding only `OPTIONS permitAll` | Missing CORS response headers | Configure `CorsConfigurationSource` and processor |
| Relying only on `@CrossOrigin` when security blocks early | `HandlerMapping` is never reached | Configure CORS inside/before Security |
| Using Servlet `CorsFilter` in WebFlux | Wrong type/lifecycle | Use `CorsWebFilter`/reactive `CorsConfigurationSource` |
| `allowedMethods` has `OPTIONS` without `GET` | Preflight asking for `GET` is still rejected | Declare actual methods `GET`/`POST` |
| Forgetting `Authorization` in `allowedHeaders` | Preflight for Bearer request gets 403 | Allowlist `Authorization` |
| Using `exposedHeaders` instead of `allowedHeaders` | Browser cannot send the header | Distinguish request vs. response headers |
| Setting `allowedOrigins` `"*"` with `allowCredentials` `true` | Invalid and insecure configuration | Use an exact origin allowlist |
| Overly broad `allowedOriginPatterns` | Unintended browser origins permitted | Restrict patterns and test |
| Duplicating `CorsWebFilter` and `http.cors` with differing policies | Unpredictable headers/behavior | Maintain one clear primary CORS source |
| Multiple `SecurityWebFilterChain`s with CORS on only one | `OPTIONS` hits the wrong chain and fails | Verify matchers/order/preflight |
| Custom auth `WebFilter` running before CORS | Preflight is still blocked | Adjust order or integrate into Security |
| Disabling CSRF to fix preflight | Loses protection on state-changing actions | Diagnose CORS and CSRF separately |
| Disabling all authorization to fix 401 | Endpoints become unprotected | Keep actual requests authenticated |
| Ignoring scheme/port in origins | Local dev or HTTPS origins blocked | Declare exact origins |
| Gateway blocking `OPTIONS` | Spring never receives preflight | Fix gateway/proxy method policy |
| Browser reports CORS when actual returns 500 | Misdiagnosis | Inspect Network tab and server logs |
| Testing only controllers with unit tests | Filter/security ordering goes unverified | Use `WebTestClient` integration tests |
| Assuming `curl` tests browser CORS | Misses enforcement failures | Combine `curl` header checks with browser tests |

## 17. Pre-Production Checklist

1. Are frontend origins allowlisted accurately by scheme/host/port?
2. Are all actual methods included in `allowedMethods`?
3. Are all request headers actually used (`Authorization`/`Content-Type`/custom headers) included in `allowedHeaders`?
4. Does `allowCredentials` match the cookie/token model rather than being enabled unnecessarily?
5. Are wildcard origins absent when credentials are enabled?
6. Is preflight handled before authentication/authorization?
7. Is there one consistent primary CORS policy without conflicting processors?
8. Do all `SecurityWebFilterChain` beans handle preflight properly per `securityMatcher` and `@Order`?
9. Do any custom `WebFilter` beans block `OPTIONS` before CORS?
10. Do `@CrossOrigin`/`addCorsMappings` (if present) avoid conflicting with Security's CORS policy?
11. Are `OPTIONS` preflights unblocked by gateways/CDNs/WAFs?
12. Do actual requests without authentication still return 401?
13. Do actual requests without authorization still return 403?
14. Is CSRF properly protecting state-changing methods when using sessions/cookies?
15. Are valid origins, denied origins, and disallowed methods/headers tested?
16. Are credential-less preflights, credentialed actual requests, and unauthenticated actual requests tested?
17. Does logging omit `Authorization`/cookies/tokens?
18. Are preflight failures and actual 401/403 counts monitored after deployment?

**Summary:** A preflight is an HTTP `OPTIONS` request carrying `Origin` and `Access-Control-Request-Method`, normally without cookies or `Authorization`. In Spring WebFlux, the CORS processor must handle it before authentication/authorization; use `ServerHttpSecurity.cors(configurationSource)` or an early-ordered standalone `CorsWebFilter`. `@CrossOrigin` and `WebFluxConfigurer.addCorsMappings` operate at `HandlerMapping`, which can be too late if security blocks earlier. CORS neither authenticates users nor replaces CSRF: actual requests must still pass authorization checks, and `POST`/`PUT`/`PATCH`/`DELETE` may still require CSRF tokens depending on the credential model. Test the full filter chain with `WebTestClient` over real HTTP to avoid fixing the wrong layer.

## References

- Spring Security 6.5 — Reactive CORS Integration: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html
- Spring Security — WebFlux Security and WebFilter Architecture: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework — WebFilter in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security — ServerHttpSecurity.CorsSpec API: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Boot 3.5 — Test WebFlux with WebTestClient: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Security — CSRF in Reactive Applications: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Boot 3.5.16 release (baseline example): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
