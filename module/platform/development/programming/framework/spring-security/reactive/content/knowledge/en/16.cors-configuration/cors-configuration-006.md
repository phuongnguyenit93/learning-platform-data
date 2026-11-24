# allowCredentials, Explicit Origins, and Wildcard Limitations

## Learning Objectives

This lesson belongs to the **CORS Configuration** group of **Spring Security reactive / WebFlux**. After this lesson, you will be able to:

- Explain **origin** accurately (scheme + hostname + port), distinguish **same-origin** from **same-site**, and understand why two apps on `localhost` on different ports are still cross-origin.
- Understand the effect of `CorsConfiguration.setAllowCredentials(true)` and the `Access-Control-Allow-Credentials: true` header on requests carrying **cookies, HTTP authentication, and browser credentials**.
- Distinguish `allowedOrigins` (exact origin list) from `allowedOriginPatterns` (conditional origin patterns), and understand the strict limitation on `"*"` when credentials are enabled.
- Read and explain `OPTIONS` preflights with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`, along with CORS response headers.
- Configure CORS in a **reactive `SecurityWebFilterChain`** using `CorsConfiguration` and `UrlBasedCorsConfigurationSource`, so preflight runs **before authentication checks**.
- Run a **Java 17 + Spring WebFlux + Spring Security** example, call the API from a JavaScript app on another origin, and test with `WebTestClient`/`curl`.
- Avoid mistakes such as using wildcards with credentials, reflecting arbitrary Origins, overly broad CORS policies, forgetting `credentials: "include"`, confusing CORS with CSRF, and misconfiguring cookie `SameSite`/`Secure`.

> **Scope:** Spring Security **reactive** uses `ServerHttpSecurity` and `SecurityWebFilterChain`. Do not copy Servlet MVC's `HttpSecurity` or `CorsFilter` verbatim. The examples separate standalone runnable code from snippets used to illustrate errors or alternative configurations.

## 1. First: What Is an Origin?

An **origin** is defined by the tuple:

~~~text
origin = scheme + hostname + port
~~~

Examples:

| URL | Origin | Compared to `http://localhost:8080` |
|---|---|---|
| `http://localhost:8080/api/me` | `http://localhost:8080` | Same-origin |
| `http://localhost:8080/static/app.html` | `http://localhost:8080` | Same-origin (a different path does not change the origin) |
| `http://localhost:3000` | `http://localhost:3000` | Cross-origin due to **different port** |
| `https://localhost:8080` | `https://localhost:8080` | Cross-origin due to **different scheme** |
| `https://api.example.test` | `https://api.example.test` | Cross-origin |
| `https://ui.example.test` | `https://ui.example.test` | Cross-origin with `https://api.example.test` even if same-site |

**Paths do not belong to an origin.** The HTTP `Origin` value consists of scheme, host, and port per protocol rules; it omits `/api/me` or query strings. Default scheme ports may be normalized/omitted in representation.

**Same-site does not equal same-origin.** Cookie `SameSite` uses the concept of *site* (schemeful site in modern browsers), whereas CORS uses *origin*. Two subdomains can be same-site yet still cross-origin, requiring CORS when JavaScript reads responses across them.

### 1.1. Why Do Browsers Need CORS?

The **Same-Origin Policy (SOP)** restricts JavaScript at origin A from reading responses from origin B. **Cross-Origin Resource Sharing (CORS)** is the set of headers allowing the server at B to tell the browser under what conditions origin A may read the response.

For example, a page at `http://localhost:3000` sends a request to a backend at `http://localhost:8080`:

~~~javascript
const response = await fetch("http://localhost:8080/api/me");
const user = await response.json();
~~~

If the backend does not send CORS headers for the UI origin, the browser blocks JavaScript from accessing the response. This **does not mean** the backend never received the request or never ran business logic: certain cross-origin requests can still be sent. CORS is primarily a mechanism **enforced by the browser on response sharing**, not authentication, authorization, or a network firewall.

HTTP clients like `curl` do not enforce browser SOP; they can read responses even without CORS headers. Always inspect both **response headers** and **browser** behavior when debugging.

## 2. What Does allowCredentials Actually Mean?

In Spring Framework WebFlux:

~~~java
CorsConfiguration config = new CorsConfiguration();

config.setAllowedOrigins(
    List.of("http://localhost:3000"));
config.setAllowCredentials(true);
~~~

This is a **snippet inside a configuration method** with imports `org.springframework.web.cors.CorsConfiguration` and `java.util.List`. When the request origin matches and other CORS conditions pass, the server may send:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

This is a **header excerpt**; the framework may also emit `Vary: Access-Control-Request-Method, Access-Control-Request-Headers` and other headers.

**`allowCredentials(true)` does not authenticate anyone on its own.** It allows CORS responses to be exposed to JavaScript when requests include credentials under browser rules, yet:

- It **does not create sessions** or issue cookies automatically.
- It **does not force the browser to send cookies**; JavaScript must also set the appropriate `credentials` mode, and cookies must satisfy Path/Domain/SameSite/Secure and browser policies.
- It **does not verify passwords**, JWT signatures, session IDs, roles, or business permissions.
- It **does not bypass CSRF** or turn unsafe POSTs into safe ones.
- It **does not govern who may call the API with curl/Postman**; non-browser clients do not enforce CORS.

### 2.1. From the Fetch API Perspective

When a page at `http://localhost:3000` calls a backend at `http://localhost:8080`:

~~~javascript
const response = await fetch("http://localhost:8080/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

`credentials: "include"` allows the browser to **send credentials** in a cross-origin request **if** all other cookie/credential policies permit it. For cross-origin requests, the default `same-origin` **does not** send cookies for the target origin as desired in this example.

On the backend, it must respond with the exact origin and `Access-Control-Allow-Credentials: true`. If any condition is missing, the request may reach the server, yet the browser will withhold the response from JavaScript.

| Fetch credentials mode | When requesting another origin | Notes |
|---|---|---|
| `omit` | Does not send credentials | Suitable for public APIs that do not rely on cookies |
| `same-origin` | Does not send browser credentials on cross-origin requests | Default value of `fetch` |
| `include` | Permits sending per cookie/browser policies | Cannot override SameSite, Secure, third-party cookie blocking, or CORS policy |

**Do not mistake `include` for "ignoring all browser policies".** If a browser blocks third-party cookies, changing `credentials` alone will not make cookies flow. If the response lacks valid CORS headers, the browser still refuses JS access.

### 2.2. The Credentials Header and Responses

Common header pair:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
~~~

The value `true` for `Access-Control-Allow-Credentials` is the only valid literal string; there is no `Access-Control-Allow-Credentials: false` with equivalent meaning. When credentialed access is disallowed, the server normally **omits this header** rather than sending `false`.

Do not assume that seeing `Set-Cookie` in a response means JavaScript can read the cookie or the browser accepted it. Cookies also depend on `HttpOnly`, `Domain`, `Path`, `Secure`, `SameSite`, and browser policies; `Set-Cookie` is a forbidden response-header name for the JS Fetch API.

## 3. Why Can't credentials=true Be Combined with allowedOrigins("*")?

Common misconfiguration:

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(true); // INVALID
~~~

Per Spring Framework's `CorsConfiguration` and the CORS specification, when credentials are enabled, `Access-Control-Allow-Origin` **must not be `*`**. If a server returns:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

the browser refuses to share the response with the credentialed request. Spring Framework also **rejects** combining `allowedOrigins("*")` with `allowCredentials(true)` during validation and can throw `IllegalArgumentException` when validating or handling requests depending on how the configuration is used.

**The right approach:** declare explicit origins, or use `allowedOriginPatterns` under controlled rules, returning the **validated actual origin** for the request.

### 3.1. Safest Configuration: Fixed List

~~~java
config.setAllowedOrigins(List.of(
    "https://app.example.test",
    "https://admin.example.test"));
config.setAllowCredentials(true);
~~~

If a request arrives from `https://app.example.test`, a valid CORS response can be:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

If a request arrives from `https://evil.example.test`, the server must not return an allow header for that origin; invalid preflights are typically rejected. **Never** send a comma-separated list of origins in `Access-Control-Allow-Origin`: the response header represents **one specific origin or `*`**, not a string like `https://a,https://b`.

### 3.2. When Not Using Credentials: Wildcards Can Be Valid

For a **public** resource requiring no cookies/HTTP authentication and containing no personal data:

~~~java
CorsConfiguration publicCors = new CorsConfiguration();
publicCors.setAllowedOrigins(List.of("*"));
publicCors.setAllowedMethods(List.of("GET"));
publicCors.setAllowCredentials(false);
~~~

Spring can respond with:

~~~http
Access-Control-Allow-Origin: *
~~~

That is a different design from credentialed CORS. Do not slap a public origin wildcard onto a user-data endpoint assuming roles or authentication compensate for every response-sharing risk. If an API uses a manually attached Bearer token, verify the Fetch credentials mode, auth mechanism, and exposed data; do not apply a wildcard without assessing your threat model.

## 4. allowedOrigins vs. allowedOriginPatterns

Two APIs with similar names behave quite differently:

| Property | Expected input | With `allowCredentials(true)` | Header when matched |
|---|---|---|---|
| `setAllowedOrigins(...)` | List of **exact origins**, or literal `*` | Supported with explicit origins; **not** with `*` | Exact origin, or `*` when non-credentialed |
| `setAllowedOriginPatterns(...)` | List of **patterns** supporting host wildcards and port lists in Spring syntax | Supported when the pattern is trusted and scoped | **Actual matched origin**, not the pattern or `*` |

Example when multiple managed subdomains must be supported:

~~~java
config.setAllowedOriginPatterns(List.of(
    "https://*.trusted.example.test"));
config.setAllowCredentials(true);
~~~

When a request from `https://shop.trusted.example.test` matches, Spring returns:

~~~http
Access-Control-Allow-Origin: https://shop.trusted.example.test
Access-Control-Allow-Credentials: true
~~~

**Caution:** this is a pattern illustration; if a subdomain is hijacked or assigned to an untrusted tenant, the wildcard pattern turns that origin into one **allowed to read credentialed responses**, creating severe exposure. Prefer a finite allowlist. Never use pattern `"*"` merely to dodge the validation error of `allowedOrigins("*")`—even though the API emits a concrete header, the policy matches every origin.

### 4.1. Port and Scheme Patterns

Spring Framework supports patterns such as:

~~~text
https://*.example.test
https://*.example.test:[8080,8443]
https://*.example.test:[*]
~~~

These are **illustrative configuration values**. Port wildcard `[*]` can be handy for local testing, yet widens the permitted surface; restrict to actual ports in production. `https://...` does not implicitly allow `http://...`; the scheme is part of the origin and must match.

Do not treat `allowedOriginPatterns` as an arbitrary regex accepting URL paths. It is an origin pattern in Spring CORS semantics. Accidentally writing `https://*.example.test/any/path` puts a path where only an origin is expected and must be fixed.

### 4.2. Right vs. Wrong "Origin Reflection"

A compliant CORS processor may **echo** the request's `Origin` as `Access-Control-Allow-Origin` **after matching it against a safe allowlist or pattern**. That is not arbitrary reflection.

**Dangerous mistake:**

~~~java
// ANTI-PATTERN - never use in production.
String origin = exchange.getRequest().getHeaders().getOrigin();
exchange.getResponse().getHeaders()
    .set("Access-Control-Allow-Origin", origin);
exchange.getResponse().getHeaders()
    .set("Access-Control-Allow-Credentials", "true");
~~~

This is an **anti-pattern snippet**, not a complete application. It trusts every `Origin` header and can grant a malicious site permission to read user data responses whenever the browser sends credentials. The server must validate `Origin` against a trusted allowlist **before** emitting the header.

### 4.3. Null Origin

Environments such as sandboxed iframes, `file://`, or opaque-origin documents can send `Origin: null`. Never default to allowing literal `"null"` or wildcards to "make CORS work" without understanding the request source; that can admit untrusted origins.

## 5. Wildcard Limitations Go Beyond allowedOrigins

In Spring Framework and CORS, `*` carries **different semantics** depending on where it appears:

| Configuration / Header | When `credentials=true` | Key takeaway |
|---|---|---|
| `allowedOrigins("*")` → `Access-Control-Allow-Origin: *` | **Invalid** | Must return an explicit origin or pattern-matched origin |
| `allowedOriginPatterns("https://*.trusted...")` | Can be valid | Server emits the matched request origin; keep patterns narrow |
| `allowedMethods("*")` | Spring may **echo the method** requested in preflight | Does not mean every business method is authorized |
| `allowedHeaders("*")` | Spring may **echo the header list** requested in preflight | Better to restrict to accepted headers |
| `exposedHeaders("*")` | Has browser/spec compatibility nuances; Spring may emit `*` | For credentialed APIs, prefer an explicit list to avoid ambiguity |
| `Access-Control-Allow-Origin: *` in HTTP response | Browser blocks credentialed response | Cannot be fixed merely by setting `include` on the frontend |

Spring Framework documentation explains that when `allowCredentials=true` and `allowedHeaders` or `allowedMethods` contains `*`, Spring **echoes** the preflight headers/methods rather than emitting literal `*`. This differs from `allowedOrigins`. Meanwhile, `exposedHeaders("*")` has real-world compatibility caveats, so use a fixed exposed-header allowlist for sensitive data.

**Recommendation:** in real systems, declare finite sets of origins, HTTP methods, request headers, and response headers that are actually required. `*` is a data-sharing decision needing review, not a "fix browser error button".

## 6. OPTIONS Preflight: Why Must CORS Run Before Spring Security?

Browsers send a **preflight** when a cross-origin request uses a non-CORS-safelisted method or header, such as a GET with `X-Client-Trace` or a JSON POST with `Content-Type: application/json`.

A preflight request looks like:

~~~http
OPTIONS /api/me HTTP/1.1
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-client-trace
~~~

Standard preflights **do not send cookies or session credentials**. They ask the server whether this origin may send a GET with that custom header. If Spring Security requires authentication **before** CORS runs, preflight is rejected with 401 even when the actual request would carry a valid session. This is a very common misconfiguration.

With proper configuration, the preflight response can be:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: x-client-trace
Access-Control-Max-Age: 1800
Vary: Origin
~~~

This is an **expected excerpt**; 200 vs. 204 status, capitalization, `Vary` list, header ordering, and cache details vary by runtime. Having no `Set-Cookie` in preflight is normal; **preflight is not a login**.

Only if preflight succeeds does the browser send the **actual request**. The actual request can still receive 401/403 from Authentication/Authorization or be blocked by CSRF—**CORS passing does not mean the business API passes**.

### 6.1. Key Preflight Headers

| Header | Direction | Role |
|---|---|---|
| `Origin` | Client → Server | Origin of the JavaScript initiating the request |
| `Access-Control-Request-Method` | Browser → Server | HTTP method intended for the actual request |
| `Access-Control-Request-Headers` | Browser → Server | Non-safelisted request headers intended to be sent |
| `Access-Control-Allow-Origin` | Server → Browser | Origin allowed to read the response |
| `Access-Control-Allow-Credentials` | Server → Browser | Permits sharing a credentialed response |
| `Access-Control-Allow-Methods` | Server → Browser | HTTP methods allowed under CORS |
| `Access-Control-Allow-Headers` | Server → Browser | Request headers allowed under CORS |
| `Access-Control-Max-Age` | Server → Browser | How long preflight decisions may be cached, capped by the browser |
| `Vary` | Server → Cache | Tells caches to distinguish responses by Origin/method/headers when policy varies |

### 6.2. Vary: Origin Matters for Caches and CDNs

A backend returns origin A for requests from A and origin B for requests from B. If a CDN caches A's response and serves it to B without checking `Vary: Origin`, CORS can break or cause resource-sharing issues. When a server uses an explicit origin list and echoes the validated origin, include `Vary: Origin`, and for preflights potentially `Access-Control-Request-Method`/`Access-Control-Request-Headers`.

**CORS headers do not provide cache isolation for user data.** For responses personalized by cookies or authorization, add appropriate cache policies like `Cache-Control: private/no-store` as needed; never rely on `Vary: Origin` alone.

### 6.3. Do Not "Fix" Preflight with permitAll on Every URL

If `OPTIONS /api/me` returns 401, the right fix is configuring an **early-running CORS processor/filter** and allowing the right Origin/method/headers. Writing `anyExchange().permitAll()` or removing Authentication is wrong. While some setups configure matchers for `OPTIONS`, that never replaces CORS header validation.

## 7. Configuring CORS for Spring Security Reactive

Spring Security reactive integrates with Spring Framework's CORS support. Per the reference docs, you can declare a `UrlBasedCorsConfigurationSource` bean from `org.springframework.web.cors.reactive` and enable CORS integration in `ServerHttpSecurity`:

~~~java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(List.of(
        "http://localhost:3000",
        "https://portal.example.test"));
    config.setAllowCredentials(true);
    config.setAllowedMethods(List.of("GET", "OPTIONS"));
    config.setAllowedHeaders(List.of("X-Client-Trace"));
    config.setExposedHeaders(List.of("X-Trace-Id"));
    config.setMaxAge(1800L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}

@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .cors(Customizer.withDefaults())
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

These are **two configuration methods placed inside a Spring class with imports** (the complete application is in section 8). Decisions to understand clearly:

1. `setAllowedOrigins(...)` permits **exactly** two origins, not every website.
2. `setAllowCredentials(true)` permits credentialed responses under CORS.
3. `setAllowedMethods(...)` allows only GET and OPTIONS in this illustration; production should list exact API methods.
4. `setAllowedHeaders(...)` allows only the custom `X-Client-Trace` header in the example's preflight; real JSON POSTs will need `Content-Type`/`X-XSRF-TOKEN` as appropriate.
5. `setExposedHeaders(...)` lets the frontend read `X-Trace-Id` (without needing `*`).
6. `registerCorsConfiguration("/api/**", config)` applies the CORS policy to API URLs, not necessarily to `/login` or static resources.
7. `.cors(Customizer.withDefaults())` integrates CORS into the security chain using the configuration source bean. Do not also register a second custom `CorsWebFilter` for the same URLs when integrating this way.
8. `authorizeExchange(...)` continues to protect the API after preflight, independently of `allowCredentials`.

### 7.1. CorsWebFilter and @CrossOrigin

You can also use a WebFlux `CorsWebFilter` bean when early CORS processing is needed, or `@CrossOrigin`/WebFlux MVC-style handler mappings on controllers. However, know precisely which layer handles preflight ahead of security, and avoid overlapping CORS configuration sources.

- WebFlux's `CorsWebFilter` resides in `org.springframework.web.cors.reactive`; do not use Servlet's `org.springframework.web.filter.CorsFilter`.
- `@CrossOrigin(origins=..., allowCredentials="true")` is an option on controllers for narrow policies, yet with security filters active you must ensure preflight runs in the proper order.
- Global and local configurations can merge under Spring's rules, sometimes widening allowed origins unexpectedly. For credentialed APIs, manage policies centrally and audit extra annotations.
- Never enable the same CORS policy at both a gateway and the application in a way that duplicates `Access-Control-Allow-Origin` headers. Browsers reject responses containing conflicting or duplicated origin header values.

### 7.2. With Multiple SecurityWebFilterChains

If you have separate chains for `/api/**` and `/web/**`, define matchers and `@Order` clearly. `CorsConfigurationSource`, CORS integration, and exception handling must target the right chain; endpoints outside a matcher may miss the CORS headers you expect. Never attach a wildcard policy to a catch-all chain just to silence frontend errors.

## 8. Runnable Java 17 Demo: Session Cookie and CORS from a Port 3000 Frontend

This example uses **Java 17**, **Spring Boot 3.5.16**, Spring Security reactive, and WebFlux. The configuration demonstrates a frontend origin `http://localhost:3000` accessing a backend at `http://localhost:8080`, sending session cookies via `credentials:"include"`. The lab enables both form login (for the browser) and HTTP Basic (for easy curl testing), though production should enable only the mechanisms actually needed.

**Features:**

- `GET /api/public`: public API, no Authentication required.
- `GET /api/me`: authenticated API; returns username and demo header `X-Trace-Id`.
- `GET /login`: Spring Security-generated login form; log in as `learner` with password `demo-pass`.
- CORS `allowCredentials=true`, **only** for `http://localhost:3000` or `https://portal.example.test`.
- Static frontend `index.html` served **on port 3000**, calling the port 8080 API via `fetch`.

### 8.1. Structure

~~~text
webflux-cors-credentials-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/java/example/CorsCredentialsDemo.java
│   └── test/java/example/CorsCredentialsIntegrationTest.java
└── ui/
    └── index.html
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-cors-credentials-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
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

Requires JDK 17+ and a compatible Gradle/Gradle Wrapper. Spring Boot manages Spring Security, Reactor, and Spring Framework versions; do not mix disparate versions manually for this exercise.

### 8.2. Complete Backend

File `src/main/java/example/CorsCredentialsDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class CorsCredentialsDemo {

    public static void main(String[] args) {
        SpringApplication.run(CorsCredentialsDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Plaintext strictly for localhost demo; production must hash passwords.
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Origin includes scheme + host + port; no trailing slash.
        cors.setAllowedOrigins(List.of(
            "http://localhost:3000",
            "https://portal.example.test"));

        cors.setAllowCredentials(true);
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(List.of("X-Client-Trace"));
        cors.setExposedHeaders(List.of("X-Trace-Id"));
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .cors(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @RestController
    static class Api {

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            exchange.getResponse().getHeaders().set(
                "X-Trace-Id", "local-demo-trace");

            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }
    }
}
~~~

**Reading the code by responsibility:**

- `UrlBasedCorsConfigurationSource` is from the **reactive** package. CORS config applies to `/api/**`, so preflights for `/api/me` are evaluated against the allowlist.
- `cors.setAllowedOrigins(List.of(...))` lists two explicit origins; **never** combine `*` with `allowCredentials=true`.
- `setAllowedHeaders(List.of("X-Client-Trace"))` allows the JS custom header, causing GET to trigger preflight. Since GET has no JSON `Content-Type`, `Content-Type` is unnecessary in the demo's `allowedHeaders`.
- `setExposedHeaders(List.of("X-Trace-Id"))` lets JS read the demo response header via `response.headers.get(...)`.
- `setMaxAge(1800L)` is a preflight cache hint, not a session or token TTL; browsers may cap the cache duration.
- `.cors(Customizer.withDefaults())` integrates with Security to process preflight **before authentication**.
- `.formLogin(Customizer.withDefaults())` provides a login page for browsers; never treat a raw username query parameter as a principal.
- `.httpBasic(Customizer.withDefaults())` merely simplifies HTTP client/automated tests. In real apps, remove Basic if only form/session login is used.
- `/api/me` requires valid Authentication. A CORS allowlist never grants outsiders permission to read anyone's identity.

### 8.3. Frontend Running on Another Origin

File `ui/index.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebFlux Credentialed CORS Demo</title>
</head>
<body>
  <h1>Cross-origin request with credentials</h1>

  <p>Sign in to the backend at
     <a href="http://localhost:8080/login"
        target="_blank" rel="noopener">
        http://localhost:8080/login
     </a>
     using learner / demo-pass (localhost only).
  </p>

  <button id="callApi">Call /api/me</button>
  <pre id="result" aria-live="polite"></pre>

  <script type="module">
    "use strict";

    const api = "http://localhost:8080";

    document.getElementById("callApi")
      .addEventListener("click", async () => {
        const target = document.getElementById("result");
        target.textContent = "Requesting...";

        try {
          const response = await fetch(api + "/api/me", {
            method: "GET",
            mode: "cors",
            credentials: "include",
            headers: {
              "X-Client-Trace": "browser-demo"
            }
          });

          const contentType =
            response.headers.get("Content-Type") || "";

          if (!response.ok ||
              !contentType.includes("application/json")) {
            throw new Error("HTTP " + response.status
              + ": login required, or API did not return JSON");
          }

          const data = await response.json();
          const traceId = response.headers.get("X-Trace-Id");

          target.textContent = JSON.stringify(
            { data, traceId }, null, 2);
        } catch (error) {
          target.textContent = String(error.message || error)
            + " — check Network/CORS and exact cookies.";
        }
      });
  </script>
</body>
</html>
~~~

**Localhost model:** open the UI at `http://localhost:3000` and the API at `http://localhost:8080`. The two origins differ by port, though they are same-site for many cookie policies. Click the login link to open the **backend page** on origin 8080, enter the demo credentials, then return to the UI and click **Call /api/me**.

The frontend **does not read `HttpOnly` cookies via `document.cookie`**. The browser manages the login cookie and sends it under `credentials:"include"` if cookie policies permit. `X-Client-Trace` is only a demo header, not a credential; it intentionally triggers a browser preflight so learners can observe it.

### 8.4. Starting Both Apps

Terminal 1, in the project directory:

~~~bash
gradle bootRun
~~~

With Gradle Wrapper: `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

Terminal 2, in `webflux-cors-credentials-demo/ui`, if Python 3 is installed:

~~~bash
python -m http.server 3000
~~~

Open `http://localhost:3000`, sign in via the port 8080 backend link, and then call the API. In Browser Developer Tools → Network, you can observe:

1. `OPTIONS http://localhost:8080/api/me` (preflight, **no** cookie), carrying `Origin`, requested method GET, and requested header `x-client-trace`.
2. Preflight response containing `Access-Control-Allow-Origin: http://localhost:3000` and `Access-Control-Allow-Credentials: true`.
3. Actual `GET http://localhost:8080/api/me`, carrying the session cookie if login succeeded.
4. Actual response returning JSON with `"username":"learner"`, plus `X-Trace-Id` readable thanks to `Access-Control-Expose-Headers`.

If step 4 fails because you are not logged in, the response may be a login redirect or 401 depending on entry points and request headers; the client might see a CORS error on the login page **which is outside the `/api/**` policy**. That does not mean the backend disabled Authentication. First verify the login session works at 8080, then check CORS for `/api/me`.

**Do not use demo settings on real networks:** `{noop}` passwords and plain HTTP without TLS are strictly for localhost testing. Production requires password hashing, HTTPS, `Secure`/`HttpOnly` cookies, CSRF protection, reviewed origin restrictions, and proper session management.

## 9. Verifying with curl: Inspecting Exact Headers

HTTP clients like curl **do not enforce CORS like a browser**, yet are very useful for inspecting which headers the server emits.

### 9.1. Valid Preflight

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: http://localhost:3000' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: X-Client-Trace'
~~~

What to look for:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: X-Client-Trace
~~~

This is an **expected header excerpt**; casing and 200 vs. 204 status depend on runtime. Preflight needs no `Authorization` or cookies because browser preflight carries no credentials.

### 9.2. Preflight from a Disallowed Origin

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/me' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: X-Client-Trace'
~~~

With Spring's default CORS processor, invalid preflights usually return **403**. `Access-Control-Allow-Origin: https://evil.example.test` must not be present. A real browser may report only "CORS blocked" even though the server generated that status.

### 9.3. Valid Actual Request

~~~bash
curl -i -u learner:demo-pass \
  -H 'Origin: http://localhost:3000' \
  -H 'X-Client-Trace: curl-demo' \
  'http://localhost:8080/api/me'
~~~

Because HTTP Basic test auth succeeds, the request returns **200** along with `Access-Control-Allow-Origin: http://localhost:3000`, `Access-Control-Allow-Credentials: true`, and JSON containing the username. **Curl does not prove the browser can send session cookies**, though it proves API authentication and CORS headers operate independently.

### 9.4. Actual Request from an Unapproved Origin

~~~bash
curl -i -u learner:demo-pass \
  -H 'Origin: https://evil.example.test' \
  'http://localhost:8080/api/me'
~~~

Spring's CORS processor can directly reject the disallowed origin with 403; at minimum, it must never emit headers allowing that origin. In all cases, the browser will refuse JavaScript on that origin permission to read credentialed responses when CORS policy denies it.

**Never assume an API is secure just because the browser reports a CORS error.** If the API fails to enforce sessions, roles, or CSRF, requests from non-browser clients can still cause side effects. CORS is a browser isolation layer, not a substitute for server-side authorization.

## 10. Integration Tests with WebTestClient

The tests below verify three boundaries: **preflight is not blocked by HTTP authentication**, **untrusted origins are rejected**, and **actual authenticated requests receive proper CORS headers**.

File `src/test/java/example/CorsCredentialsIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsCredentialsIntegrationTest {

    @Autowired
    WebTestClient client;

    private static final String GOOD_ORIGIN = "http://localhost:3000";
    private static final String BAD_ORIGIN = "https://evil.example.test";

    @Test
    void acceptedPreflightRequiresNoAuthentication() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "X-Client-Trace")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().valueContains(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                "X-Client-Trace");
    }

    @Test
    void untrustedOriginPreflightIsDenied() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, BAD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "X-Client-Trace")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void validCredentialsFromAllowedOriginReceiveCORSHeaders() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .headers(headers ->
                headers.setBasicAuth("learner", "demo-pass"))
            .header("X-Client-Trace", "test-client")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().valueEquals("X-Trace-Id",
                                      "local-demo-trace")
            .expectHeader().valueContains(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                "X-Trace-Id")
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }

    @Test
    void publicRouteAcceptsAllowedOriginWithoutCredentials() {
        client.get().uri("/api/public")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectBody()
            .jsonPath("$.access").isEqualTo("public");
    }

    @Test
    void sameOriginStyleRequestNeedsNoCORSHeaders() {
        client.get().uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("learner", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

With Gradle Wrapper, use `./gradlew test` or `gradlew.bat test`. These checks are expected to pass on the given configuration, yet **must be run in practice to confirm**. The tests do not launch a browser or verify `SameSite` cookie policies; add end-to-end browser tests for production integration.

**Suggested test extensions:**

- Preflight from a valid origin requesting a header **not** in `allowedHeaders`.
- Method outside `allowedMethods`.
- Unconfigured `Origin: null`.
- Valid origin with insufficient role → Authorization still returns 403.
- Browser credentialed fetch when cookie `SameSite` blocks it.
- HTTPS frontend calling an HTTP backend triggering mixed-content blocking.
- Reverse proxy/CDN preserving `Vary: Origin` and not mis-caching personalized responses.

## 11. CORS and CSRF Must Be Kept Separate

A dangerous misconception is **"We restricted `allowedOrigins`, so we can disable CSRF"**. Both mechanisms have different goals:

| Mechanism | Primary question |
|---|---|
| Authentication | Which principal owns this request? |
| Authorization | Is the principal permitted to view/modify this resource? |
| CORS | Which origin's JavaScript may the browser allow to **read responses** from cross-origin resources? |
| CSRF | Was a state-changing request carrying automatic browser credentials genuinely initiated by the legitimate app/user? |
| SameSite cookies | In which cross-site contexts may the browser attach cookies? |
| CSP/XSS defenses | Can untrusted script execute inside an allowed origin? |

CORS normally **does not stop all ways of sending an HTTP request**. A malicious site can still submit an HTML form POST, and the browser may attach cookies per policy. If the backend relies on cookies/sessions, apply CSRF tokens or Origin checking per your threat model. **A CORS allowlist never replaces CSRF.**

### 11.1. Credentialed JSON POST

A legitimate JavaScript client may perform:

~~~javascript
await fetch("https://api.example.test/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-XSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ itemId: 42 })
});
~~~

This is an **illustrative JS snippet**, assuming `csrfToken` was obtained by the frontend through a valid CSRF token issuance flow; **it is not a POST endpoint included in the section 8 Java demo**. The backend simultaneously needs:

1. CORS allowlist for the frontend origin with `allowCredentials` true.
2. `allowedMethods` containing `POST`, and `allowedHeaders` containing `Content-Type` and `X-XSRF-TOKEN`.
3. Valid session/token authentication and a valid CSRF token per repository/request handler.
4. Resource/business authorization, input validation, and proper transaction handling.

Do not blindly enable `allowedHeaders("*")` or `allowedMethods("*")` to skip designing those boundaries.

### 11.2. SameSite Cannot Fix Broken CORS

If the frontend is at `https://ui.example.test` and the API is at `https://api.example.test`, they are different origins yet same-site by schemeful site. `SameSite=Lax` **can** permit cookies on same-site requests, yet **CORS is still required** to allow the UI origin and `allowCredentials` so JS can read the response.

If the frontend and API reside on genuinely different sites, `SameSite=Lax` cookies can be withheld on cross-site subresource fetches. `SameSite=None; Secure` may be needed under a carefully reviewed design, though browsers can still block third-party cookies even with `None; Secure`. Never mark every cookie cross-site merely to "fix CORS".

### 11.3. HTTPS and Mixed Content

A page served from `https://ui.example.test` calling `http://api.example.test` can be blocked by the browser as **mixed content** before you ever see CORS responses. Use HTTPS for both UI and API in production. `Secure` cookies are not sent over plain HTTP on normal networks (localhost has certain browser exceptions, but never rely on them for production).

## 12. Common Real-World Mistakes

**Mistake 1 — `setAllowCredentials(true)` combined with `allowedOrigins("*")`.**

Invalid per Spring and CORS. Switch to an explicit origin list. Do not substitute `allowedOriginPatterns("*")` if the goal is simply opening every source.

**Mistake 2 — Setting `Access-Control-Allow-Origin` to the request's `Origin` without validation.**

This is allow-all disguised as dynamic reflection. Reflect only after checking against a trusted allowlist/pattern.

**Mistake 3 — Granting all subdomains read access to session data.**

A hijacked or externally managed subdomain becomes a trusted origin. Audit wildcard patterns, tenant subdomains, and subdomain takeover risks.

**Mistake 4 — Allowing two origins via a comma-separated header.**

`Access-Control-Allow-Origin: https://a.test, https://b.test` is not a valid list syntax. The server must match the request `Origin` and return **one** origin.

**Mistake 5 — Omitting `credentials:"include"` in cross-origin JavaScript.**

Server `allowCredentials(true)` does not force the browser to send cookies. Set the right Fetch credentials mode, and still check `SameSite`/`Secure`/`Domain`/`Path`.

**Mistake 6 — Thinking `credentials:"include"` fixes `Access-Control-Allow-Origin:"*"`.**

No. The browser blocks credentialed responses when ACAO is `*`.

**Mistake 7 — `OPTIONS` preflight gets 401 because Spring Security runs before CORS.**

CORS must run before Authentication, as standard preflights carry no cookies. Use WebFlux CORS integration/filters properly.

**Mistake 8 — Setting `permitAll` across the entire API "for preflight".**

Very dangerous: `anyExchange().permitAll()` strips authorization from resources. Configure CORS properly instead of dropping auth.

**Mistake 9 — CORS works yet the API returns 403 due to CSRF.**

Preflight approval does not guarantee POST carries a valid CSRF token. Keep CSRF enabled when browsers use cookies/sessions.

**Mistake 10 — Testing only with curl and claiming the browser definitely works.**

Curl lacks SOP and does not enforce browser CORS, `SameSite`, or mixed content. Test both server headers and real browsers.

**Mistake 11 — Checking only hostname while forgetting scheme or port.**

`http://localhost:3000` differs from `http://localhost:8080`; HTTPS differs from HTTP; the port in an origin matters.

**Mistake 12 — Unconditionally allowing `Origin: null`.**

An opaque or sandboxed origin can report `null`. Never treat `null` as equivalent to a trusted frontend.

**Mistake 13 — Enabling `exposedHeaders("*")` without review.**

For credentialed CORS, browsers and specs have compatibility nuances; explicitly list the headers the frontend actually needs to read.

**Mistake 14 — Improper `Vary`/`Cache-Control`.**

When ACAO varies by `Origin`, `Vary: Origin` is needed; personalized data requires dedicated cache policies to prevent leakage via CDNs/proxies.

**Mistake 15 — Two CORS filters emitting headers simultaneously.**

CORS configured in a gateway + framework + custom middleware can duplicate header values, causing browsers to reject the response. Maintain a single governed policy source.

**Mistake 16 — Configuring WebMVC `CorsFilter` in a WebFlux app.**

Use reactive `CorsWebFilter`/`UrlBasedCorsConfigurationSource` or integrate via `ServerHttpSecurity.cors(...)`.

**Mistake 17 — Disabling or tweaking CORS to "protect an API from curl".**

CORS is not a network block and cannot stop custom HTTP clients. Enforce Authentication, Authorization, rate limiting, and server-side input validation.

**Mistake 18 — Forgetting headers in preflight.**

The frontend sends `X-XSRF-TOKEN` or `Authorization` while the config allows only `Content-Type`; the browser blocks before sending the actual request. Add the exact required headers and test.

**Mistake 19 — Using credentials with a wildcard on user-specific GETs.**

Beyond violating the protocol, it signals an overly permissive data-sharing policy; permit only official origins.

**Mistake 20 — Treating a 200 preflight as proof the user is authenticated.**

Preflights carry no credentials. Authentication happens separately on the actual request; a 200 preflight grants zero business permissions.

## 13. Pre-Production Review Checklist

1. **Inventory:** List the frontend origins that **genuinely** need to call the API, including scheme/host/port for every environment.
2. **Credential model:** Does the API use session cookies, HTTP Basic, Bearer tokens, or a combination? Confirm the right Fetch credentials mode and browser behavior.
3. **Allow credentials:** Call `setAllowCredentials(true)` only when credentialed CORS is truly required, never by habit.
4. **Allowed origins:** Use an explicit origin list; never `*` when credentials are true.
5. **Patterns:** If wildcard subdomains are necessary, verify domain ownership, tenant model, TLS, ports, and takeover risk; enforce strict bounds.
6. **Preflight:** `OPTIONS` from allowed origins must be processed before authentication.
7. **Allowed methods:** Permit only the GET/POST/PUT/PATCH/DELETE methods actually needed; avoid needless wildcards.
8. **Allowed headers:** List `Content-Type`, `Authorization`, `X-XSRF-TOKEN`, or other headers per actual client needs.
9. **Exposed headers:** List only the response headers the frontend needs; do not default to `*`.
10. **Access-Control-Allow-Origin:** Return the single matched origin, never a comma-separated list or arbitrary Origin reflection.
11. **Cache:** Appropriate `Vary: Origin`; personalized responses are never cached by a CDN for other users.
12. **CSRF:** When browser credentials are sent automatically, enforce proper CSRF token/Origin checks; never disable CSRF just because CORS passes.
13. **Cookies:** `SameSite`/`Secure`/`Domain`/`Path`/`HttpOnly` match sessions, HTTPS, and cross-site architecture.
14. **Origin null:** Disallowed unless a trusted, explicitly reviewed use case exists.
15. **Same-site vs. same-origin:** Never assume subdomains or ports automatically bypass CORS.
16. **Multiple chains:** CORS policy applied to the right `SecurityWebFilterChain`, with no duplicate filter/gateway writes.
17. **Authentication:** Passing CORS never bypasses login, disabled-user checks, or token validation.
18. **Authorization:** A trusted origin never replaces role, ownership, or tenant checks.
19. **Browser QA:** Tested in real browsers covering UI origin, API origin, cookies, and error responses.
20. **Regression:** Tests cover allowed/disallowed origins, preflights, allowed/disallowed headers/methods, credentialed GETs, and CSRF POSTs.
21. **Operational controls:** Sanitized logs/metrics, rate limiting, TLS, secrets management, and never logging raw cookies/tokens.
22. **Change management:** When onboarding a new frontend origin, review ownership and threat model instead of adding `*` for speed.

## 14. Knowledge Check

**1.** Does `allowCredentials(true)` make the browser automatically send cookies on every cross-origin fetch?

**Answer:** No. The frontend needs `credentials:"include"` for cross-origin calls, and cookies must still satisfy browser policies. The server header only permits sharing credentialed responses.

**2.** Can `setAllowedOrigins(List.of("*"))` be used together with `setAllowCredentials(true)`?

**Answer:** No. Spring and browsers forbid wildcard ACAO with credentials; use an explicit allowlist or tightly governed origin patterns.

**3.** How does `allowedOriginPatterns("https://*.trusted.example.test")` differ from `allowedOrigins("*")` in the response?

**Answer:** When a pattern matches, Spring returns the **specific matched origin**, not literal `*`. However, broad patterns can still be unsafe, especially with untrusted subdomains.

**4.** Why must preflights not require a session cookie?

**Answer:** Standard browser preflights do not send credentials. CORS must process preflight before authentication, or valid calls can fail erroneously with 401.

**5.** Can `Access-Control-Allow-Origin` contain `https://a.example,https://b.example`?

**Answer:** No. The server checks `Origin` and returns a single valid origin, or `*` in non-credentialed cases.

**6.** A UI at `https://ui.example.test` and API at `https://api.example.test` are same-site—is CORS still needed?

**Answer:** Yes, because they have different origins. Cookie `SameSite` and CORS use two different concepts.

**7.** The browser sends a cookie-authenticated POST and CORS allows the origin. Is a CSRF token still needed?

**Answer:** For cookie-authenticated state-changing requests, CSRF protection is still needed per your threat model. CORS only governs response reading, not anti-forgery defense.

**8.** The server returns 200 for preflight. Does that prove the user is logged in?

**Answer:** Not yet. Preflight carries no credentials; the separate actual request performs Authentication and Authorization.

**9.** What happens when JS running on `localhost:3000` calls `localhost:8080` without `credentials:"include"`?

**Answer:** Despite sharing the same host, they have different origins due to port. Under default `same-origin`, `fetch` does not send cross-origin credentials, so the session API may see an anonymous user.

**10.** Can wildcard methods/headers be configured with `allowCredentials(true)` in Spring?

**Answer:** With `allowedMethods("*")` or `allowedHeaders("*")`, Spring can echo the methods/headers requested in preflight instead of emitting literal `*`. Still, production should use finite lists; `allowedOrigins("*")` remains forbidden when credentials are true.

**11.** If curl reads the API from an evil origin, has CORS failed?

**Answer:** Cannot conclude that. Curl does not enforce browser SOP/CORS; inspect server headers and test in a browser. Server-side Authentication/Authorization remain mandatory.

**12.** Can a cross-origin GET without preflight reach the server while JavaScript is blocked from reading the response?

**Answer:** Yes. The browser can send the request and then prevent the script from reading the response if the CORS policy fails. This is why CORS alone is insufficient against CSRF.

## Official Documentation

- Spring Security — CORS for Reactive Applications: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Framework — CORS in WebFlux, Credentialed Requests, Global Configuration: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework — `CorsConfiguration` API (allowedOrigins, allowedOriginPatterns, allowCredentials): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Security 6.5 — `ServerHttpSecurity` CORS DSL: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- MDN — CORS, Credentialed Requests and Wildcards: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Fetch Request credentials mode: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN — SameSite cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
