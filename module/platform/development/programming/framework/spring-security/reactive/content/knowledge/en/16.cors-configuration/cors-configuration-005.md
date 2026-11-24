# Declaring Required Origins, Methods, Headers, and exposedHeaders

> **Parent topic:** CORS Configuration in **Spring Security reactive / Spring WebFlux**. This lesson explains how to properly configure `allowedOrigins`, `allowedMethods`, `allowedHeaders`, `exposedHeaders`, `allowCredentials`, and `maxAge` via `CorsConfiguration` / `UrlBasedCorsConfigurationSource`, integrate with `ServerHttpSecurity.cors(...)`, exercise browser preflight, and test with `WebTestClient`. The practice code uses **Java 17+, Spring Boot 3.x, Spring Framework 6.x, and Spring Security 6.x**.

## 1. Objectives

After this lesson, you will be able to:

1. Distinguish **same-origin policy**, **cross-origin requests**, **CORS preflight**, **actual requests**, and CORS versus authentication/authorization.
2. Identify an origin by **scheme + host + port**, without confusing origins with paths or wildcards.
3. Properly declare **HTTP methods** browsers may use cross-origin via `setAllowedMethods(...)`.
4. Declare **request header names** browsers may send via `setAllowedHeaders(...)`, such as `Authorization`, `Content-Type`, and `X-Request-Id`.
5. Declare **response header names** the frontend may read via `setExposedHeaders(...)`, such as `ETag`, `Location`, and `X-Request-Id`.
6. Know when `allowCredentials(true)` is appropriate, why it must not be combined with `allowedOrigins("*")`, and cookie/CSRF considerations.
7. Place CORS processing **before Spring Security authentication** for `OPTIONS` preflight without mistakenly opening APIs via `permitAll()`.
8. Build a complete WebFlux example and test allowed or rejected origins, methods, headers, and `Access-Control-*` response headers.
9. Understand why `curl` can call an API even when a browser reports a CORS error, and why CORS is **not** a firewall or a replacement for authorization.
10. Review configurations under the principle of **minimum necessary cross-origin access**, separating development from production.

## 2. What Is an Origin?

The origin of a web page is the **scheme, host, port** tuple. Two URLs share the same origin when this tuple matches.

| Page running at | API called at | Same origin? |
| --- | --- | --- |
| `https://app.example.com/home` | `https://app.example.com/api/items` | **Yes**, differing paths do not create a new origin |
| `https://app.example.com` | `https://api.example.com` | **No**, different hostname |
| `http://localhost:5173` | `http://localhost:8080` | **No**, different port |
| `https://app.example.com` | `http://app.example.com` | **No**, different scheme |
| `https://app.example.com` | `https://app.example.com:8443` | **No**, different port |
| `https://app.example.com/page` | `https://app.example.com/other` | **Yes**, same scheme/host/port |

When browser JavaScript accesses a resource at another origin, the browser enforces the **same-origin policy** and CORS: the server can permit specific origins to read responses using `Access-Control-Allow-Origin` and related CORS headers.

**Important:** CORS is a policy **checked by browsers on cross-origin requests**; it does not block `curl`, `WebClient`, server-to-server clients, or an attacker calling the API directly. If an endpoint requires login, roles, scopes, or tenants, you must use **Spring Security authentication and authorization** independently of CORS.

### 2.1 Origins Do Not Include Paths or Trailing Slashes

A valid configuration:

```java
configuration.setAllowedOrigins(
    List.of("https://app.example.com", "http://localhost:5173")
);
```

Do not configure `"https://app.example.com/dashboard"` or `"https://app.example.com/"` as a standard origin; the browser's `Origin` header contains only scheme, host, and port (with special cases like `Origin: null` that require separate security review). `https://app.example.com` **differs** from `http://app.example.com`, and dev port `5173` **differs** from dev port `3000`.

## 3. Five Key Parameter Groups in CorsConfiguration

Spring Framework's `CorsConfiguration` holds the CORS policy. Its methods have similar names but distinct responsibilities:

| Java Property | Corresponding CORS Header | Governs |
| --- | --- | --- |
| `setAllowedOrigins(List<String>)` | `Access-Control-Allow-Origin` | Which origins are permitted to read cross-origin responses |
| `setAllowedMethods(List<String>)` | `Access-Control-Allow-Methods` | Which **actual HTTP methods** are permitted in cross-origin requests |
| `setAllowedHeaders(List<String>)` | `Access-Control-Allow-Headers` | Which **request header** names the frontend may send |
| `setExposedHeaders(List<String>)` | `Access-Control-Expose-Headers` | Which **response header** names frontend JavaScript may read |
| `setAllowCredentials(Boolean)` | `Access-Control-Allow-Credentials` | Whether credentialed cross-origin requests are allowed at the CORS layer |
| `setMaxAge(Long)` | `Access-Control-Max-Age` | How long the browser is advised to cache preflight results, in seconds |
| `setAllowedOriginPatterns(List<String>)` | Usually echoes the matched origin | Dynamic origin matcher supporting hostname wildcards; scope must be tightly controlled |

**Most commonly confused points:**

- `allowedHeaders` does **not** specify which response headers the frontend may read; that is `exposedHeaders`.
- `exposedHeaders` does **not** allow the frontend to send request headers; that is `allowedHeaders`.
- `allowedMethods` lists **actual GET/POST/PATCH... methods**; there is no need to add `OPTIONS` merely because preflight uses HTTP OPTIONS.
- `allowedOrigins` does not decide which users may access a route; it only affects browser CORS.
- `allowCredentials` does not create sessions/cookies or verify passwords. It is solely a CORS policy about sending credentials and letting JS read credentialed responses.

### 3.1 allowedOrigins: Prefer an Explicit List

Example for dev and production frontends:

```java
config.setAllowedOrigins(List.of(
    "http://localhost:5173",
    "https://app.example.com"
));
```

This is a **configuration snippet** that belongs inside a Spring bean. In production, omit localhost origins unless genuinely needed—for example, by separating them with Spring profiles and controlled external configuration. Never read an arbitrary origin from an HTTP request and echo it back automatically into the response.

If only one trusted web app exists, a **single exact-origin** list is usually better than a wildcard.

### 3.2 allowedOriginPatterns: When Needed, Use With Caution

For example, you can write:

```java
config.setAllowedOriginPatterns(
    List.of("https://*.example.com")
);
```

Spring matches the incoming origin against the pattern and can return **the actual matched origin** in `Access-Control-Allow-Origin`, rather than requiring browsers to interpret a wildcard pattern string. However, permitting **all subdomains** can include unprotected subdomains, hijacked subdomains, or untrusted tenant pages. When paired with cookies or credentials, the risk is even higher.

**Preference:** an exact-origin allowlist. Use patterns only when you have real hostname/tenant governance and control ownership of every matched host. Never take a tenant host directly from `Origin` and treat it as authenticated.

### 3.3 allowedMethods: Declare Per Business Contract

```java
config.setAllowedMethods(List.of(
    "GET", "POST", "PATCH"
));
```

A preflight for `PATCH /api/items/42` sends **HTTP OPTIONS** with `Access-Control-Request-Method: PATCH` to ask whether the **actual** PATCH is permitted. Therefore, only `PATCH` needs to be in `allowedMethods` for that check; `OPTIONS` is not required in the list just to allow preflight.

If your application only serves GETs, do not blindly open POST/PUT/DELETE. If different routes need different access levels, register **distinct `CorsConfiguration`s per path** or define security rules per method. The CORS method allowlist is only a browser restriction, not authorization.

### 3.4 allowedHeaders: Header Names the **Client Wants to Send**

```java
config.setAllowedHeaders(List.of(
    "Authorization",
    "Content-Type",
    "X-Request-Id",
    "X-CSRF-TOKEN"
));
```

A preflight might contain:

```http
OPTIONS /api/items HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-request-id
```

The browser is asking: may the frontend from this origin send a **POST** with those **request headers**? The server allows it only when origin, method, and headers satisfy policy. HTTP header names are case-insensitive by protocol, so tests should compare case-insensitively.

Key notes:

- `Authorization` is the request header for Basic/Bearer; **list it explicitly** if a cross-origin frontend needs to send it.
- `Content-Type: application/json` usually triggers preflight because it is not a CORS-safelisted `Content-Type` value.
- `X-CSRF-TOKEN` is needed for browser CSRF token flows by design; permitting it in CORS **does not automatically satisfy CSRF protection**.
- `X-Request-Id` is a tracing header if properly designed and input-validated; never trust it as proof of authentication.
- Do not list `Origin`, `Access-Control-Request-Method`, or `Access-Control-Request-Headers` as a way to "enable" preflight. Those are browser/protocol headers of CORS requests themselves, not custom application headers sent by client code.

### 3.5 exposedHeaders: Header Names **JS Wants to Read from the Response**

```java
config.setExposedHeaders(List.of(
    "X-Request-Id", "ETag", "Location"
));
```

For instance, after a valid API call, the frontend may need to:

- Read `X-Request-Id` to correlate a support request.
- Read `ETag` to support caching or conditional requests.
- Read `Location` after creating a resource if a POST returns 201 with `Location`.

The server can send `ETag` and `X-Request-Id` normally, yet **cross-origin JavaScript cannot read them** unless they are CORS-safelisted response headers or listed in `Access-Control-Expose-Headers`. `ETag` and `Location` are practical examples of headers that must be exposed explicitly.

Response headers readable by default under CORS belong to the safelisted group: `Cache-Control`, `Content-Language`, `Content-Length`, `Content-Type`, `Expires`, `Last-Modified`, and `Pragma`. You do not have to add all of them to `exposedHeaders`, though you may list them for consistency. `Set-Cookie` is a **forbidden response-header name**: adding it to `exposedHeaders` **does not let `fetch().headers.get("set-cookie")` read cookies**. Cookies are managed separately by the browser and governed by `SameSite`, `Secure`, and third-party cookie restrictions.

### 3.6 maxAge: Caching Preflight Results

```java
config.setMaxAge(1800L); // 1800 seconds = 30 minutes
```

Browsers can cache preflight results so they do not repeat `OPTIONS` for the same type of request every time. `Access-Control-Max-Age` is a **hint**; browsers may enforce their own upper caps and caching policies. When you update a CORS allowlist, clients may continue using cached preflights until expiry. Balance performance against policy revocation responsiveness.

## 4. Preflight and Actual Requests Differ

### 4.1 Flow with Preflight

A JavaScript client sends a JSON POST with custom headers to a different API origin:

```text
Frontend https://app.example.com
       |
       | fetch("https://api.example.com/api/items",
       |       { method:"POST", headers:{
       |            "Content-Type":"application/json",
       |            "Authorization":"Bearer ...",
       |            "X-Request-Id":"..."
       |       }})
       |
       v
Browser sends OPTIONS preflight:
       Origin: https://app.example.com
       Access-Control-Request-Method: POST
       Access-Control-Request-Headers:
           authorization,content-type,x-request-id
       |
       v
CORS processor checks origin + method + headers
       |
       +-- allowed     -> returns 2xx + Access-Control-Allow-*
       |                   browser may now send actual POST
       |
       +-- disallowed  -> browser blocks actual request
       |
       v
Actual POST with credentials (if sent by client)
       |
       v
Spring Security authentication/authorization/CSRF
       |
       +-- 2xx/4xx/5xx per business logic
       |
       v
Browser checks Access-Control-Allow-Origin and credential policy
       |
       v
JS may read response/body and permitted exposedHeaders
```

**Preflight is not login.** It only confirms CORS policy for the upcoming request. Preflights typically **do not carry session cookies or Basic credentials**, so they must be processed **before Spring Security rejects anonymous requests**, rather than demanding `ROLE_USER` on an `OPTIONS` endpoint.

### 4.2 Requests Not Requiring Preflight

A cross-origin GET whose headers and `Content-Type` meet *CORS-safelisted* rules may skip preflight; the browser still sends `Origin` and checks `Access-Control-Allow-Origin` on the **actual response**. The absence of `OPTIONS` does not mean the request was same-origin or that CORS is disabled.

A GET carrying a frontend-set `Authorization` header typically requires preflight because `Authorization` is not a CORS-safelisted request header. A POST sending `Content-Type: application/json` also typically triggers preflight.

### 4.3 HTTP Header Distinction Table

| Header | Request or response? | Stage where used |
| --- | --- | --- |
| `Origin` | Request browser → API | Identifies the cross-origin caller |
| `Access-Control-Request-Method` | Preflight `OPTIONS` request | Browser asks about the **actual request's** method |
| `Access-Control-Request-Headers` | Preflight `OPTIONS` request | Browser asks about request headers it intends to send |
| `Access-Control-Allow-Origin` | Preflight/actual response | Server approves the origin |
| `Access-Control-Allow-Methods` | Preflight response | Permitted cross-origin methods |
| `Access-Control-Allow-Headers` | Preflight response | Permitted request header names |
| `Access-Control-Expose-Headers` | Actual response | Response header names JS is allowed to read |
| `Access-Control-Allow-Credentials` | Response when credentials enabled | Browser may expose a credentialed response to JS |
| `Access-Control-Max-Age` | Preflight response | Duration browser may cache the result |
| `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` | Response/cache hint | Helps caches distinguish matching CORS variants |

**Do not confuse them:** `Access-Control-Allow-Headers` is not a list of response headers for JS. `Access-Control-Expose-Headers` does not permit a request header. If the API sends `X-Request-Id` properly yet the frontend cannot read it, you usually need **`exposedHeaders`**, not `allowedHeaders`.

## 5. Why Spring Security Reactive Must Process CORS Early

CORS preflights normally carry no user authentication data. If WebFlux Security demands authentication before preflight is handled, the browser can receive **401** instead of a valid CORS preflight response, and the actual request will never be sent.

Spring Security WebFlux integrates CORS via `ServerHttpSecurity.cors(...)`, using a `CorsConfigurationSource` and handling it with `CorsWebFilter`. In Spring Security **6.1+**, the clean style is:

```java
.cors(Customizer.withDefaults())
```

When a compatible **`CorsConfigurationSource` bean** exists in the application context, Spring Security picks it up to wire CORS support into the chain. Using `cors(...configurationSource(source))` provides the source explicitly without relying on bean discovery.

Spring Security documentation states the rule: **CORS must be processed before authentication**, because preflight lacks ordinary cookies/identity. Never solve this with **`anyExchange().permitAll()`**, as that exposes your entire API.

### 5.1 Three Integration Approaches: Do Not Mix Arbitrarily

**Approach A — Recommended in this lesson:** a `UrlBasedCorsConfigurationSource` bean with `http.cors(Customizer.withDefaults())`. Ideal when you want a single place managing CORS for the security chain.

**Approach B — Registering a `CorsWebFilter` bean** with a source. This is standard Spring WebFlux and useful when both annotated and functional endpoints need CORS, especially very early in processing.

**Approach C — `WebFluxConfigurer.addCorsMappings(...)`** or `@CrossOrigin` at controller/handler mapping. Useful for WebFlux `HandlerMapping`-level CORS, provided you verify preflight **is not blocked by security before reaching `HandlerMapping`**.

**Avoid** stacking A, B, and C together without a deliberate design; they can produce conflicting policies, duplicate headers, and confusion over which layer allowed or blocked a request. Choose one central configuration source aligned with your security pipeline and write integration tests for `OPTIONS`.

## 6. Complete Java 17+ Project: Declaring All Four Core CORS Groups

This example includes:

- Cross-origin access allowed for **development** frontend `http://localhost:5173` and production frontend `https://app.example.com`.
- `/api/items` API supporting GET and POST. GET requires role `READER`; POST requires role `EDITOR`.
- CORS allows GET, POST, PATCH on `/api/**`, and only the four required request headers.
- JavaScript can read three response headers: `X-Request-Id`, `ETag`, and `Location`.
- HTTP Basic uses **demo credentials** to demonstrate authentication/authorization. In real products, consider OAuth2/OIDC or a trusted BFF/session architecture.
- CSRF is **not disabled**. Hence the demo test for POST without a CSRF token returns 403 even though POST preflight is allowed. This proves CORS does not replace security.

### 6.1 Dependencies and Project Layout

Create a Spring Boot **3.x**, Java **17+**, Gradle Groovy project with Spring Reactive Web, Spring Security, and Spring Boot Test.

Here is the `dependencies` section in `build.gradle` from a project generated via Spring Initializr with the Spring Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the **WebFlux server**; adding `spring-boot-starter-web` alongside it usually causes Spring Boot to select MVC/Servlet by default. `ServerHttpSecurity` / `SecurityWebFilterChain` belong to reactive server configuration, not Servlet `HttpSecurity` / `SecurityFilterChain`.

Project layout:

```text
src/main/java/com/example/corsreactive/
  CorsReactiveApplication.java
  SecurityCorsConfig.java
  ItemController.java
src/test/java/com/example/corsreactive/
  CorsIntegrationTest.java
```

### 6.2 CorsReactiveApplication.java

`src/main/java/com/example/corsreactive/CorsReactiveApplication.java`:

```java
package com.example.corsreactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsReactiveApplication.class, args);
    }
}
```

### 6.3 SecurityCorsConfig.java

`src/main/java/com/example/corsreactive/SecurityCorsConfig.java`:

```java
package com.example.corsreactive;

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
public class SecurityCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        var config = new CorsConfiguration();

        // 1. Exact scheme + host + port, NO path.
        config.setAllowedOrigins(List.of(
            "http://localhost:5173",
            "https://app.example.com"
        ));

        // 2. ACTUAL methods; OPTIONS preflight is handled separately.
        config.setAllowedMethods(List.of(
            "GET", "POST", "PATCH"
        ));

        // 3. Request headers the frontend needs to send.
        config.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-Request-Id",
            "X-CSRF-TOKEN"
        ));

        // 4. Response headers the frontend is allowed to read.
        config.setExposedHeaders(List.of(
            "X-Request-Id", "ETag", "Location"
        ));

        // Demo does not use cross-origin cookies: keep credentials disabled.
        config.setAllowCredentials(false);
        config.setMaxAge(1800L);

        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            // Use the source bean above for Spring Security CORS.
            .cors(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/items")
                    .hasRole("READER")
                .pathMatchers(HttpMethod.POST, "/api/items")
                    .hasRole("EDITOR")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-password"))
            .roles("READER", "EDITOR")
            .build();

        return new MapReactiveUserDetailsService(reader, editor);
    }
}
```

**How to read each part:**

1. `CorsConfiguration` holds the CORS settings; lists are set **explicitly**, without calling `applyPermitDefaultValues()` because that method can introduce overly permissive wildcard defaults for credential-protected APIs.
2. `UrlBasedCorsConfigurationSource` is the **reactive** class from `org.springframework.web.cors.reactive`. Registering `/api/**` limits this policy strictly to the intended API routes.
3. The bean returns `UrlBasedCorsConfigurationSource` so Spring Security WebFlux detects a compatible `CorsConfigurationSource`. `.cors(Customizer.withDefaults())` integrates CORS handling into the security chain.
4. The CORS method allowlist includes `PATCH` even though the demo controller has no `PATCH` handler. That **neither creates a `PATCH` route nor grants authorization**, and `anyExchange().denyAll()` still blocks `PATCH`. This clearly illustrates the boundary between browser CORS policy and server authorization.
5. `setAllowCredentials(false)` is the conservative choice when cross-origin cookies/sessions are not needed. If the browser runs `fetch(..., credentials: "include")`, this config **is insufficient** for the browser to expose the response; a dedicated credentialed policy must be designed as in section 10.
6. `httpBasic(...)` is purely for creating test users with credentials. Never put real passwords in frontend JavaScript or use Basic over plain HTTP on real networks. For browsers and OAuth2 Bearer tokens, replace HTTP Basic with a properly configured and validated Resource Server.
7. `anyExchange().denyAll()` enforces **authorization**, not CORS. GET/PATCH/POST are blocked by security based on principal, roles, method, and CSRF even when CORS permits the origin.

### 6.4 ItemController.java: Returning Response Headers to Expose

`src/main/java/com/example/corsreactive/ItemController.java`:

```java
package com.example.corsreactive;

import java.net.URI;
import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ItemController {

    public record ItemView(String id, String name) {}
    public record CreateItem(String name) {}

    @GetMapping(
        value = "/api/items",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<List<ItemView>> listItems() {
        return ResponseEntity.ok()
            .header("X-Request-Id", "req-demo-001")
            .header(HttpHeaders.ETAG, "\"items-v1\"")
            .body(List.of(new ItemView("item-1", "Example")));
    }

    @PostMapping(
        value = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<ItemView>> create(
            @RequestBody Mono<CreateItem> request) {
        return request.map(body ->
            ResponseEntity
                .created(URI.create("/api/items/item-2"))
                .header("X-Request-Id", "req-demo-002")
                .body(new ItemView("item-2", body.name()))
        );
    }
}
```

Explanation:

- `X-Request-Id` is a response header generated by the **application** for demo purposes. Calling `setExposedHeaders(List.of("X-Request-Id", ...))` lets browser JS read it from a valid cross-origin response.
- `ETag` is a response header for caching/conditional requests; since it is in `exposedHeaders`, the frontend can read it.
- `Location` is returned by `ResponseEntity.created(...)` after a successful POST. It is also listed in `exposedHeaders`.
- `ItemView` and `CreateItem` are **nested Java records**, declared inside `ItemController` and serialized/deserialized by Jackson in Spring Boot 3.x.
- CORS alone does not make POST succeed: the `EDITOR` role and CSRF protection are still enforced by Spring Security. A POST missing a CSRF token gets 403 **before the controller executes**.
- The code illustrates HTTP/CORS only, not database-backed CRUD, so POST returns a fixed demo ID. Real projects need validation, persistence, unique/random IDs, and tenant authorization.

## 7. Observing CORS with curl: Valid and Invalid Preflights

Run the application from the Gradle project:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

By default, without changing `server.port`, the backend runs at `http://localhost:8080`. Use local HTTP with dummy accounts for learning; real environments require **HTTPS/TLS**.

### 7.1 Allowed Preflight

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

An **expected** response per the CORS configuration:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH
Access-Control-Allow-Headers: authorization,content-type,x-request-id
Access-Control-Max-Age: 1800
Vary: Origin
```

This **illustrates the key headers**, not normalized byte-for-byte raw output. Spring may emit multiple `Vary` fields, different ordering, or add `Access-Control-Request-Method` and `Access-Control-Request-Headers`; CORS header values may vary in order or casing depending on implementation. Check header presence and semantics rather than matching the entire response verbatim.

**Observation:** The `OPTIONS` request carries no `Authorization`, yet it receives a valid CORS preflight response because CORS runs before HTTP Basic login is demanded. This **does not allow** the actual POST to skip login.

### 7.2 Origin Outside the Allowlist

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET"
```

Spring's `CorsWebFilter` with the default CORS processor **rejects invalid preflights** (typically HTTP 403). The browser will not send the corresponding actual request. Never blindly reflect the request's `Origin` into `Access-Control-Allow-Origin` to "fix" errors.

### 7.3 Disallowed Method

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: DELETE"
```

`DELETE` is not in `allowedMethods`, so preflight is rejected. This differs from Spring Security `denyAll()` blocking an actual DELETE; preflight can terminate in the CORS filter **before** authorization.

### 7.4 Disallowed Header

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-admin-bypass"
```

`X-Admin-Bypass` is not in `allowedHeaders`. The invalid preflight is rejected. Allowing a request header in CORS **does not mean trusting its value**: even if you add it to `allowedHeaders`, the backend must still **never** use an untrusted header to grant admin access.

### 7.5 Actual GET with HTTP Basic

```bash
curl -i -u reader \
  -H "Origin: https://app.example.com" \
  "http://localhost:8080/api/items"
```

Enter demo password `reader-demo-password` when curl prompts. Expected response:

```text
HTTP 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id, ETag, Location
X-Request-Id: req-demo-001
ETag: "items-v1"

[{"id":"item-1","name":"Example"}]
```

This is an **illustrative format**; exact header order/formatting and JSON are controlled by Spring/Jackson. `curl` **does not enforce browser CORS policy**; it prints even unexposed headers. `Access-Control-Expose-Headers` matters because **browser JavaScript** is blocked from reading `ETag`, `Location`, and `X-Request-Id` unless they are exposed.

If you call the actual GET **without Basic credentials**, the response can still include `Access-Control-Allow-Origin` while returning **401 Unauthorized**: passing CORS does not mean passing authentication.

## 8. WebTestClient Tests for Origins, Methods, allowedHeaders, and exposedHeaders

CORS bugs often surface only in browsers; therefore, explicitly test both **preflight** and **actual responses** in backend CI.

Create `src/test/java/com/example/corsreactive/CorsIntegrationTest.java`:

```java
package com.example.corsreactive;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CorsIntegrationTest {

    private static final String GOOD_ORIGIN =
        "https://app.example.com";

    @Autowired
    WebTestClient client;

    @Test
    void preflightAllowsConfiguredOriginMethodAndHeaders() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type,x-request-id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS, value ->
                    assertThat(value).contains("POST"))
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS, value -> {
                    String lower = value.toLowerCase(Locale.ROOT);
                    assertThat(lower).contains(
                        "authorization", "content-type", "x-request-id");
                });
    }

    @Test
    void rejectsPreflightFromDisallowedOrigin() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, "https://evil.example")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rejectsPreflightForDisallowedMethod() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rejectsPreflightWithDisallowedHeader() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "x-admin-bypass")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void actualGetExposesConfiguredResponseHeaders() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS, value -> {
                    String lower = value.toLowerCase(Locale.ROOT);
                    assertThat(lower).contains(
                        "x-request-id", "etag", "location");
                })
            .expectHeader().valueEquals("X-Request-Id", "req-demo-001")
            .expectHeader().valueEquals(HttpHeaders.ETAG, "\"items-v1\"")
            .expectBody()
            .jsonPath("$[0].id").isEqualTo("item-1");
    }

    @Test
    void allowedCorsOriginDoesNotBypassAuthentication() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void corsAllowsPostPreflightButCsrfStillProtectsActualPost() {
        client.post()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .headers(headers -> headers.setBasicAuth(
                "editor", "editor-demo-password"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"name\":\"Not created without CSRF\"}")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Test explanations:**

1. `preflightAllowsConfiguredOriginMethodAndHeaders` simulates a browser `OPTIONS` **without Basic credentials**, verifying **origin, actual method, and request headers**.
2. `rejectsPreflightFromDisallowedOrigin` verifies an arbitrary origin is not echoed.
3. `rejectsPreflightForDisallowedMethod` checks that `DELETE` is not in `allowedMethods`.
4. `rejectsPreflightWithDisallowedHeader` checks that an unallowlisted header is rejected.
5. `actualGetExposesConfiguredResponseHeaders` tests an **actual authenticated GET**, where `Access-Control-Expose-Headers` matters to browser JavaScript.
6. `allowedCorsOriginDoesNotBypassAuthentication` verifies that passing CORS still requires identity.
7. `corsAllowsPostPreflightButCsrfStillProtectsActualPost` shows `Access-Control-Allow-Methods: POST` **is not** write authorization; browser/session CSRF policies still apply. The example keeps default CSRF protection and omits a CSRF token, so POST receives 403.

Run:

```bash
./gradlew test --tests '*CorsIntegrationTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*CorsIntegrationTest'
```

These are **expected assertions based on the sample configuration**, not stdout from a build executed in this authoring environment. In applications with multiple security chains, reverse proxies, or additional CORS layers, inspect real results and update tests accordingly.

### 8.1 When Must You Test in a Real Browser?

`WebTestClient` checks response status/headers and security filters well, yet it **is not a browser**: it does not enforce the same-origin policy, cookie restrictions, or JavaScript `fetch` access-control rules. Add browser integration/E2E tests whenever:

- The frontend uses `credentials:"include"` or session cookies.
- `SameSite=None; Secure`, third-party cookie policies, or browser extensions are involved.
- The backend sits behind a CDN/reverse proxy that could cache or vary headers incorrectly.
- CORS policy varies by environment, tenant, or origin.
- Authentication redirects/OIDC logins exist or an API gateway handles preflight ahead of the backend.

## 9. Which Response Headers Can the Frontend Read?

Suppose a cross-origin browser request returns:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id, ETag, Location
Content-Type: application/json
X-Request-Id: req-demo-001
ETag: "items-v1"
```

When CORS passes, frontend JavaScript can run:

```javascript
const response = await fetch("https://api.example.com/api/items", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + accessToken,
    "X-Request-Id": requestId
  }
});

if (!response.ok) {
  throw new Error("HTTP status " + response.status);
}

const traceId = response.headers.get("X-Request-Id");
const etag = response.headers.get("ETag");
const items = await response.json();
console.log({ traceId, etag, items });
```

**This snippet illustrates a frontend using a Bearer header in a real system**; it **will not work out of the box against the HTTP Basic-only demo backend**. To support real Bearer tokens, the backend needs Spring Security OAuth2 Resource Server with matching decoder, issuer, audience, and scope validation—replacing Basic demo auth requires more than swapping a header string. Never hardcode access tokens, passwords, or API keys in published frontend code.

`response.headers.get("Location")` has a value only when the **actual response includes a `Location` header**, such as a POST that creates a resource. Listing `Location` in `exposedHeaders` does not generate that response header.

**`Set-Cookie` cannot be read:** `Access-Control-Expose-Headers: Set-Cookie` **does not** let JavaScript inspect `Set-Cookie`. The browser manages cookies internally; for session cookies, review `HttpOnly`, `Secure`, `SameSite`, credentials mode, and browser policies.

## 10. Considerations When Enabling allowCredentials(true)

The sample app uses `setAllowCredentials(false)` because it only demonstrates client-sent `Authorization` headers and does not need cross-origin session cookies. A BFF/browser app relying on session cookies may require `true`.

### 10.1 Configuration with Cross-Origin Session Cookies

Example **replacing the `CorsConfiguration` initialization**, without adding a second policy alongside it:

```java
CorsConfiguration config = new CorsConfiguration();

config.setAllowedOrigins(List.of(
    "https://app.example.com"
));
config.setAllowedMethods(List.of(
    "GET", "POST", "PATCH"
));
config.setAllowedHeaders(List.of(
    "Content-Type", "X-CSRF-TOKEN", "X-Request-Id"
));
config.setExposedHeaders(List.of(
    "X-Request-Id", "ETag", "Location"
));
config.setAllowCredentials(true);
config.setMaxAge(600L);
```

This is a **snippet** to place inside `corsConfigurationSource()` when the app genuinely needs cross-origin cookies. Do not copy it blindly into production; you must also manage sessions, CSRF, origin allowlists, and cookie policies.

In CORS responses to credentialed browser requests, the server normally needs:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Browser JavaScript typically uses `fetch(url, { credentials: "include", ... })` to send/receive cookies across origins. **CORS does not override cookie rules**: `SameSite`, `Secure`, third-party cookie restrictions, domain/path matching, and session expiry still apply. For cross-site cookies, evaluate `SameSite=None; Secure` and browser policy limits.

### 10.2 Why Not Use allowedOrigins("*") with Credentials?

The following configuration is **invalid** for credentialed CORS:

```java
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(true);
```

Spring Framework validates against combining `allowedOrigins("*")` with `allowCredentials(true)`, because `Access-Control-Allow-Origin: *` is incompatible with credentialed browser requests. When dynamic origins are required, `allowedOriginPatterns` can reflect the matched origin, yet an overly broad pattern with cookies remains dangerous. **An exact-origin allowlist for managed frontends is best.**

### 10.3 CORS Is Not CSRF Protection

Even when only `https://app.example.com` is allowlisted, another site can still attempt to trigger requests to your backend through mechanisms the browser permits sending. CORS mainly restricts cross-origin JavaScript from reading responses; it **does not prevent every kind of cross-site request with side effects**.

With browser sessions/cookies or browser-cached HTTP Basic, maintain a threat model covering **CSRF**, `SameSite`, session fixation, XSS, content security policy, and per-user authorization. Never disable `ServerHttpSecurity.csrf(...)` app-wide simply because CORS is configured.

If an API uses Bearer tokens attached manually by frontend code in a header with no ambient browser credentials, the CSRF risk profile differs—yet CORS is still not authentication. Adjust CSRF only after evaluating your exact client types and credential flows.

### 10.4 Authorization Header and allowCredentials Are Not Identical

`Authorization` is a **request header name** that must be listed in `allowedHeaders` if a browser intends to send it cross-origin. `allowCredentials` is a flag for **credentialed CORS requests under the browser's credentials mode**, specifically governing browser-managed cookies and HTTP authentication. A request with a script-added `Authorization` header does not automatically mean the config must set `allowCredentials(true)` in every scenario; verify your `fetch` credentials mode and real flow.

To avoid confusion in production, document the exact auth protocol (JS-attached Bearer, cookie session, or browser-managed HTTP Basic) and test in real browsers.

## 11. When to Add @CrossOrigin or WebFluxConfigurer?

Some apps only need to expose a few handlers:

```java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = { RequestMethod.GET },
    allowedHeaders = { "Authorization", "X-Request-Id" },
    exposedHeaders = { "ETag", "X-Request-Id" }
)
@GetMapping("/api/items")
public ResponseEntity<?> listItems() {
    // ...
}
```

**This is only an annotation snippet**, not a standalone Java class. In Spring WebFlux, `@CrossOrigin` is processed by `HandlerMapping` when a request reaches an annotated handler. If Spring Security blocks preflight **before routing**, controller annotations cannot rescue the preflight. With functional `RouterFunction`s, you must also check how CORS is applied.

Another option is `WebFluxConfigurer`:

```java
@Configuration
public class WebCorsConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PATCH")
            .allowedHeaders(
                "Authorization", "Content-Type", "X-Request-Id")
            .exposedHeaders(
                "ETag", "X-Request-Id", "Location")
            .maxAge(1800);
    }
}
```

This is a **class snippet** needing imports for `Configuration`, `WebFluxConfigurer`, and `CorsRegistry`. In Spring Boot, implementing `WebFluxConfigurer` alone suffices without adding `@EnableWebFlux`. `HandlerMapping` CORS merges with `@CrossOrigin` under framework merge rules, yet if Spring Security and WebFlux hold **two differing policies**, responses quickly become confusing. In APIs protected by Spring Security, prefer one centralized policy and test HTTP preflight.

### 11.1 Alternative CorsWebFilter Bean

If you prefer a WebFlux `WebFilter` instead of letting `ServerHttpSecurity` create/integrate the filter from a source, you can declare:

```java
@Bean
CorsWebFilter corsWebFilter() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of(
        "https://app.example.com"
    ));
    config.setAllowedMethods(List.of("GET", "POST"));
    config.setAllowedHeaders(List.of(
        "Authorization", "Content-Type"
    ));
    config.setExposedHeaders(List.of("X-Request-Id"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);

    return new CorsWebFilter(source);
}
```

**Alternative snippet** requiring imports `org.springframework.web.cors.reactive.CorsWebFilter`, `UrlBasedCorsConfigurationSource`, `CorsConfiguration`, and `List`. Do not register this `CorsWebFilter` bean alongside another Security CORS filter just to "be extra sure it runs"; choose one mechanism deliberately. Spring Security documentation recommends early CORS processing so `OPTIONS` preflight is never blocked by authentication.

## 12. Safety Rules When Using Multiple SecurityWebFilterChains

When splitting security chains by path (e.g., `/api/**` for Bearer tokens and `/web/**` for form login), CORS must also align with those matchers and chains.

- `securityMatcher` selects a request's chain in `@Order` sequence; `authorizeExchange` selects rules inside that chain.
- If the CORS source registers only `/api/**`, preflights to `/web/**` are not automatically permitted by that policy.
- If another chain accidentally matches before the CORS-enabled chain, preflight can be blocked or evaluated under a different policy.
- Maintain a **consistent CORS policy** aligned with your API's trust boundaries; for multiple origins/paths, map them explicitly and test **each actual path**.
- Never "fix" preflight with a catch-all `anyExchange().permitAll()` chain; that can expose endpoints without authentication.
- If a gateway/nginx/CDN also handles CORS, decide on **one single responsible layer**; verify it never emits two conflicting `Access-Control-Allow-Origin` headers.

### 12.1 Does OPTIONS Need permitAll()?

When CORS is handled properly by `CorsWebFilter` ahead of Spring Security authentication, valid preflights are answered **without needing** a blanket authorization rule like `pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()`.

Some architectures have custom `OPTIONS` handling and define targeted policies, yet **never** default to `permitAll` on all `OPTIONS` without checking CORS filter order, request matching, gateways, and security consequences. Preflight is specifically an `OPTIONS` request with valid `Origin` and `Access-Control-Request-Method` headers; **every `OPTIONS`** is not a preflight.

## 13. Vary, Caching, and CDNs / Reverse Proxies

When an API returns different `Access-Control-Allow-Origin` values depending on the request `Origin`, shared caches must distinguish responses properly. CORS processors typically emit headers such as:

```http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

or a single `Vary` header combining those values, depending on the server. **Never hardcode tests expecting one exact byte layout.**

If a CDN caches a response carrying `Access-Control-Allow-Origin: https://app.example.com` and replays it to another origin, browsers will reject it or encounter risks if cache keys/policies are misconfigured. For authenticated APIs, verify `Cache-Control` on user-specific content; never mis-cache sensitive bodies keyed only by URL and origin.

`Access-Control-Max-Age` is the browser's preflight cache and **does not replace** HTTP caching policy for actual responses. `ETag` supports conditional requests, and to let JS read `ETag` cross-origin, it must be exposed as shown in section 3.5.

## 14. Quick Diagnostic Table

| Symptom | Common cause | How to inspect or fix |
| --- | --- | --- |
| Browser reports CORS, curl GET still 200 | Curl does not enforce same-origin policy | Check OPTIONS/actual Origin, ACAO, and browser DevTools |
| OPTIONS preflight returns 401 | Security authentication runs before CORS | Use Spring Security CORS integration or properly ordered `CorsWebFilter` |
| Preflight returns 403 due to origin | Scheme/host/port missing from allowlist | Compare exact `Origin`, port, protocol, and env config |
| Preflight 403 for PATCH method | `allowedMethods` omits PATCH | Declare minimal needed actual methods |
| Preflight 403 when sending Authorization | `allowedHeaders` omits Authorization | Add the exact request header name |
| Actual API sends ETag yet JS cannot read it | `exposedHeaders` omits ETag | Add ETag to `setExposedHeaders` |
| JS cannot read `Location` after POST 201 | `Location` not exposed or not returned | Expose `Location` and verify actual response includes it |
| Frontend sets `credentials: "include"` yet CORS blocks | Missing/false ACAC or wildcard ACAO | Evaluate `allowCredentials(true)` with exact origins and cookie policy |
| Browser still omits cookies after CORS passes | `SameSite`/`Secure`/third-party cookie policy | Check `Set-Cookie`, site context, and browser restrictions |
| POST preflight passes yet POST returns 403 | Spring Security authz/CSRF blocks actual request | Test credentials, role, CSRF token; CORS only lets browser send |
| Only one route gets CORS | Source registered only one path or chain mismatch | Check `registerCorsConfiguration` and `securityMatcher` |
| Duplicate ACAO or conflicting headers | Both gateway and backend set CORS | Assign one owner; avoid double filters |
| `allowedOrigins("*")` + credentials true fails | Invalid per Spring/CORS spec | Use exact allowlist or controlled patterns |
| Added `Set-Cookie` to `exposedHeaders` yet unreadable | Header forbidden to JS by browser | Rely on browser cookie handling; never expose secrets |
| `Origin: null` blocked | Sandbox/file/opaque origin not allowlisted | Review threat model; do not allow `null` casually |
| Preflight still cached after policy change | `maxAge` and browser cache not expired | Account for `maxAge` when rolling out changes |
| Frontend header lookup fails due to casing | Header names are case-insensitive; code/test case-sensitive | Check standard names; `WebTestClient` compares case-insensitively |
| Resource server returns 401 after CORS passes | Invalid/expired/missing Bearer token | Fix auth separately; do not open CORS to all origins |
| Server returns 200 yet JS reports CORS | ACAO/ACAC/Vary or preflight mismatch | Use browser Network pane to inspect both preflight and actual response |

**Effective debug sequence:** Check URL, Origin, HTTP method, and request headers → inspect OPTIONS if present → inspect response `Access-Control-Allow-*` → inspect Spring Security 401/403/CSRF separately → check `Access-Control-Expose-Headers` on actual response → check cookies/proxy/CDN. Never turn on `allowedOrigins("*")` or `allowedHeaders("*")` reflexively before knowing the mismatch.

## 15. Security Pitfalls to Avoid

1. **Blindly reflecting Origin:** reading `request.getHeaders().getOrigin()` and copying it into ACAO without validation. This turns your allowlist into allowing any website.
2. **Using `allowedOrigins("*")` in cookie/credentialed APIs:** incompatible with `allowCredentials(true)` and risks leaking data to untrusted sites.
3. **Using `allowedOriginPatterns("https://*.example.com")` when subdomains are not uniformly governed:** subdomain takeover or tenant pages could gain read access.
4. **Setting `allowedMethods("*")` / `allowedHeaders("*")` to silence every error:** widens the CORS surface unnecessarily and hinders auditing. Open only what the frontend actually uses.
5. **Treating CORS as authentication:** attackers still call APIs via curl or server-to-server; enforce permissions with Spring Security and data-level authorization.
6. **Treating CORS as CSRF protection:** browsers can send cross-site requests via multiple mechanisms; evaluate cookies/sessions/CSRF separately.
7. **Making every route `permitAll` in a security chain because OPTIONS returned 401:** creates an auth bypass; fix CORS processing order instead.
8. **Letting JS read unnecessary response headers:** expose only clearly needed response headers; never try to expose `Set-Cookie` or sensitive tokens.
9. **Leaving local origins enabled in production:** `http://localhost:5173` belongs strictly in dev config when environments can be separated.
10. **Forgetting scheme or port:** `http` differs from `https`, and 5173 differs from 3000; paths are never part of an origin.
11. **Misaligned two-layer CORS configurations:** Gateway, Spring Security, and `@CrossOrigin` can produce inconsistent policies.
12. **Testing CORS only with server unit tests:** browsers also enforce credentials mode, cookie policies, and preflight caching.
13. **Skipping checks on exposed headers:** API works and the Network pane shows `ETag`, yet `response.headers.get("ETag")` returns null.
14. **Confusing `Access-Control-Allow-Headers` with `Access-Control-Expose-Headers`:** preflight passes yet the frontend still cannot read response metadata.
15. **Mis-caching user responses:** passing CORS does not make personalized responses safe for shared caches; check authorization, `Cache-Control`, and CDN settings.
16. **Unconditionally allowing `Origin: null`:** opaque origins such as sandboxed iframes or files carry weaker trust guarantees than exact web origins.
17. **Using `X-Request-Id`, `X-Tenant`, or `Origin` headers as identity proof:** request headers are client-supplied; never authorize based on them without verification.
18. **Abandoning fail-closed behavior on CORS errors:** when the browser blocks a request, fix the exact allowlist/method/header rather than switching rules to `permitAll`.

## 16. Practice Extensions

### Exercise A — Adding the `X-Correlation-Id` Header

The frontend needs to send `X-Correlation-Id` for request tracing. Add it to `setAllowedHeaders(...)`, then send a preflight with `Access-Control-Request-Headers: x-correlation-id`. Do not add it only to `exposedHeaders` because it is a **request header**. If the backend also **returns** `X-Correlation-Id` for JS to read, add it to **`exposedHeaders` as well** and write the actual response header.

### Exercise B — Exposing ETag

After a GET, the frontend needs to read `ETag` to send `If-None-Match` on a later request. `ETag` belongs in **exposed response headers**, while `If-None-Match` is a **request header** that can trigger preflight and requires checking `allowedHeaders` depending on the flow. Add `If-None-Match` when the frontend actually sends it, write preflight tests, and test caching/conditional responses if supported.

### Exercise C — Separating Dev and Production Origins

In dev, allow only `http://localhost:5173`. In production, allow only `https://app.example.com`. Implement this via controlled profile/environment configuration (e.g., `@ConfigurationProperties` or a property list) and verify upon deployment. Never let clients supply origins via input parameters or self-declared HTTP headers.

### Exercise D — Adding PATCH

The example's CORS config allows `PATCH`, yet the server has neither a `PATCH` route nor an authority rule. Implement a `PATCH /api/items/{id}` handler, a Spring Security rule requiring role `EDITOR` or write scope, proper CSRF handling, and tests for both preflight and actual `PATCH`. **A CORS-allowed method does not conjure a handler or grant authorization.**

### Exercise E — Browser Credentialed Sessions

Switch the demo to form login / session cookies over HTTPS, enable `allowCredentials(true)` for **one exact origin**, and configure CSRF plus `SameSite`/`Secure`/`HttpOnly` cookies. Test browser `fetch(..., credentials:"include")` with and without a CSRF token. Never place demo passwords or Bearer tokens in query strings.

### Exercise F — Multi-Tenancy

If each tenant has its own origin, avoid casual wildcards. Use a governed trusted-tenant registry, verify hostnames, restrict origins, and handle `Vary: Origin` caching. One tenant's origin must never automatically gain permission to read another tenant's data; authentication and tenant authorization must be enforced independently.

## 17. Self-Check Questions

**Q1.** How do `allowedHeaders` and `exposedHeaders` differ?

**Answer:** `allowedHeaders` determines **which request header names the client may send** in a cross-origin request; `exposedHeaders` determines **which response header names browser JavaScript may read**. CORS never invents headers the application did not send.

**Q2.** A browser sends an `OPTIONS` preflight for `POST /api/items`. Must `"OPTIONS"` be added to `allowedMethods` for it to succeed?

**Answer:** **Not required.** `Access-Control-Request-Method: POST` asks about the actual method `POST`; the CORS processor recognizes `OPTIONS` preflights separately.

**Q3.** Which list does the `Authorization` header belong in?

**Answer:** `allowedHeaders`, if the frontend needs to send it cross-origin. Not `exposedHeaders`, unless there is an extraordinary reason for the frontend to read an `Authorization` response header (rarely advisable).

**Q4.** The API returns `ETag` and it appears in the Network pane, yet `fetch().headers.get("ETag")` returns null. Why?

**Answer:** For cross-origin responses, check whether `Access-Control-Expose-Headers` includes `ETag`, and confirm CORS passed overall and the actual response carries `ETag`.

**Q5.** Why cannot `allowedOrigins("*")` be combined with `allowCredentials(true)`?

**Answer:** Credentialed browser requests cannot use a wildcard ACAO; Spring Framework validation rejects this combination. Use an exact allowlist or tightly controlled patterns.

**Q6.** Does a 200 CORS preflight guarantee the actual POST returns 200?

**Answer:** No. HTTP authentication, roles/scopes, CSRF, validation, handler mapping, and business errors still govern the actual POST.

**Q7.** `curl -i` reads the API even when the browser reports a CORS error. Is the server's authentication broken?

**Answer:** Cannot conclude that yet. Curl does not enforce the browser's same-origin policy; simulate preflight/`Origin` and inspect CORS response headers. Authentication is a separate layer.

**Q8.** When using cross-origin cookies, is flipping `allowCredentials(true)` enough?

**Answer:** No. You also need exact origins, browser `credentials:"include"`, cookie `SameSite`/`Secure`, CSRF protection, HTTPS, and proper authentication/session policies.

**Q9.** Does placing `@CrossOrigin` on a controller always resolve `OPTIONS` 401 before Spring Security?

**Answer:** Not guaranteed, because security WebFilters can block preflight before `HandlerMapping` reaches the controller. Integrate CORS early in the chain.

**Q10.** Does `setAllowedOriginPatterns(List.of("https://*.example.com"))` protect tenant data by itself?

**Answer:** No. It only matches origins; you must still verify user, tenant, role, and resource permissions, and control every hostname capable of matching the pattern.

## 18. Production Deployment Checklist

- [ ] **Exact origins** identified for frontends, without trailing paths, with accurate schemes and ports.
- [ ] Separate dev/staging/prod configs so localhost or untrusted tenants never leak into production.
- [ ] `allowedMethods` contains **only the actual methods** genuinely required by the API.
- [ ] `allowedHeaders` lists `Authorization`, `Content-Type`, and CSRF/tracing headers only when actually sent by the frontend.
- [ ] `exposedHeaders` lists `ETag`, `Location`, `X-Request-Id` only when JavaScript needs to read them.
- [ ] `allowCredentials` evaluated against cookies/sessions/credentials mode; never pair `allowedOrigins("*")` with `true`.
- [ ] `maxAge` set sensibly, accounting for preflight cache lag during policy rollouts.
- [ ] Spring Security WebFlux has CORS integration active **before authentication**.
- [ ] No overlapping CORS WebFilter, `HandlerMapping`, Security, and proxy headers without explicit design.
- [ ] Valid CORS preflights never get 401; invalid preflights are rejected.
- [ ] Tests cover **valid/invalid origins**, **valid/invalid methods**, **allowed/disallowed headers**, and **actual exposed headers**.
- [ ] Tests verify that allowlisted origins still require authentication and authorization.
- [ ] For browser sessions, CSRF and cookie policies are tested separately; CORS does not replace them.
- [ ] Browser E2E tests included when using `credentials:"include"` or operating behind a reverse proxy/CDN.
- [ ] Personalized HTTP responses carry proper `Cache-Control`/`Vary` headers; data is never cross-cached across users/origins.
- [ ] Secrets, API keys, Bearer tokens, and Basic passwords are never logged or placed in URLs.

## 19. Summary

To configure CORS in Spring Security WebFlux, understand and declare **four independent groups**: `allowedOrigins` (who may call from a browser), `allowedMethods` (actual HTTP methods), `allowedHeaders` (request headers browsers may send), and `exposedHeaders` (response headers JavaScript may read). With credentials, govern exact origins, cookies/CSRF, and browser credentials mode; `maxAge` optimizes preflight caching rather than granting access.

**The most important security rule:** **CORS runs before authentication for preflight, yet CORS never replaces authentication, authorization, or CSRF.** A 200 preflight does not guarantee a 200 actual request. Maintain strict security rules, use the minimal allowlist required, and test both response headers and real browser behavior.

### Official References

- [Spring Security 6.5 — Reactive CORS integration](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — ServerHttpSecurity.cors API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
- [Spring Framework — WebFlux CorsWebFilter API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html)
- [Spring Framework — WebFlux WebFilter integration](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [Fetch Standard — CORS protocol and response headers](https://fetch.spec.whatwg.org/)
