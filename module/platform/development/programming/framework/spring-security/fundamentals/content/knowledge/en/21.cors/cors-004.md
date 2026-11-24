# Allowed Origins, Methods, Headers, and Exposed Headers in CORS

> **Topic:** Spring Security – fundamentals → **CORS** (Cross-Origin Resource Sharing). This lesson uses Java 17+, Spring Boot 3.x, Spring Framework 6.x, and Spring Security 6.x to explain the **four key configuration axes**: allowed origins, allowed methods, allowed headers, and exposed headers. It also covers preflight, requests with cookies/credentials, proper configuration for Servlet MVC and WebFlux, how to test, and the boundaries between CORS, CSRF, authentication, and authorization.

## 1. What problem does CORS solve?

An **Origin** is the tuple `scheme + host + port`, for example:

- Frontend `https://app.example.com`.
- API `https://api.example.com`.
- Admin frontend `https://console.example.com`.

These three addresses may be **same-site** yet **cross-origin** because their hosts differ. Similarly, `http://localhost:3000` and `http://localhost:8080` are cross-origin due to different ports; `http://app.example.com` and `https://app.example.com` are cross-origin due to different schemes.

The **Same-Origin Policy (SOP)** restricts a page's JavaScript from accessing data from another origin. **CORS** is a mechanism based on HTTP headers by which **the target server allows the browser to share responses with a specific calling origin**, and for certain requests performs a **preflight** check before sending the actual request.

Do not treat CORS as an “API authentication firewall”:

- CORS is enforced by **the browser**; `curl` or another backend does not necessarily apply SOP/CORS.
- The server must still check authentication, roles/scopes, resource permissions, and CSRF when browsers auto-send credentials.
- CORS grants no extra database privileges, does not make JWTs/secrets valid, and does not guarantee a request came from a genuine frontend app. `Origin` is a browser-supplied signal, yet any HTTP client can craft that header itself.
- A cross-origin request whose **response reading** is blocked by the browser may still have reached the server and caused side effects, especially with HTML forms/simple requests. Thus CORS **does not replace CSRF protection**.

### 1.1. Four configuration axes

A policy typically answers:

| Question | Spring `CorsConfiguration` | Key response header |
|---|---|---|
| **Which origins** may read responses via browser? | `allowedOrigins` or `allowedOriginPatterns` | `Access-Control-Allow-Origin` |
| **Which HTTP methods** are allowed in preflight? | `allowedMethods` | `Access-Control-Allow-Methods` |
| **Which request headers** may the browser send during preflight? | `allowedHeaders` | `Access-Control-Allow-Headers` |
| **Which response headers** may JS read beyond the safelisted ones? | `exposedHeaders` | `Access-Control-Expose-Headers` |

Two accompanying attributes commonly used together:

- `allowCredentials` → `Access-Control-Allow-Credentials: true`: lets the browser expose credentialed CORS responses when other conditions are met.
- `maxAge` → `Access-Control-Max-Age`: duration the browser may cache preflight results within browser limits.

**Most important distinction:** `allowedHeaders` applies to **request headers the frontend wants to send**; `exposedHeaders` applies to **response headers JavaScript wants to read**. These are two completely opposite directions.

## 2. Allowed origins: exactly which origins can read responses?

When JavaScript running on `https://app.example.com` calls an API at `https://api.example.com`, the browser may send:

```http
GET /api/items HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
```

If the policy allows this origin, the API returns:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

[{"id":1,"name":"Notebook"}]
```

The browser uses `Access-Control-Allow-Origin` to decide whether JavaScript at the sending origin may access the response. **The server must not assume a user is authorized to access data simply because the origin is valid.** For APIs requiring authentication, responses must still pass authentication/authorization policies.

### 2.1. Origin must account for scheme, host, and port

| Sending origin | Policy allows only `https://app.example.com` | Result |
|---|---|---|
| `https://app.example.com` | Exact match | CORS allowed |
| `http://app.example.com` | Wrong scheme | No match |
| `https://app.example.com:8443` | Wrong port | No match |
| `https://console.example.com` | Wrong host | No match unless added explicitly |
| `https://app.example.com.attacker.net` | Lookalike spoofed name | No match |
| `null` | Special Origin value | Not allowed automatically |

A hand-written check like `origin.contains("example.com")` or `origin.endsWith("example.com")` can easily fail on lookalike domains, suffixes, or scheme/port mismatches. Use the CORS framework with an **exact allowlist** of trusted origins, or a carefully reviewed pattern mechanism.

### 2.2. `allowedOrigins` and wildcard `*`

`Access-Control-Allow-Origin: *` allows reading responses from any origin when requests **do not use credentials**. It is not appropriate for private APIs returning user-specific data where cookies or browser authentication are sent along.

**When `allowCredentials(true)`, do not configure `allowedOrigins(List.of("*"))`.** Browsers reject combining `Access-Control-Allow-Origin: *` with credentialed responses; Spring Framework also checks and disallows combining wildcard origin with `allowCredentials=true`. Use specific origins.

No configuration guarantees complete safety merely by using exact origins: if a trusted frontend origin suffers from XSS/takeover or a user is tricked into acting within a legitimate app, CORS does not stop actions from an already trusted source.

### 2.3. `allowedOriginPatterns` can help, yet easily becomes too broad

Spring Framework provides `allowedOriginPatterns` to match a structured set of origins, such as multiple subdomains. When a pattern matches, the framework can return the **exact matched origin** instead of `*`, enabling it to work with `allowCredentials=true`.

However, a policy like `https://*.example.com` can allow unmonitored subdomains, taken-over subdomains, or untrusted test environments to read user-specific responses. If there are only two known frontends, **using two exact origins** remains easier to audit and safer.

Do not use `null` as a convenient wildcard: sandboxed documents, `file:`, and certain opaque origins can emit `Origin: null`.

## 3. Allowed methods: which methods pass preflight?

`allowedMethods` controls which HTTP methods the browser is permitted to use during **CORS preflight** for the configured resource scope. For example, a policy has:

```text
GET
POST
PATCH
DELETE
OPTIONS
```

When the frontend wants to send a PATCH with JSON, the browser sends an `OPTIONS` preflight containing:

```http
OPTIONS /api/items/42 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-request-id
```

The server may respond:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Request-ID
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

The browser checks the requested method `PATCH` against `Access-Control-Allow-Methods` before sending the actual request. **This header does not create a PATCH endpoint** and **does not replace Spring Security authorization**: if the controller has no `@PatchMapping`, the handler may return 405/404; if the user lacks permission, the server can still return 403.

### 3.1. CORS-safelisted methods and preflight

The `GET`, `HEAD`, and `POST` methods belong to the **CORS-safelisted methods** set, yet **not every GET/POST avoids preflight**. A POST with `Content-Type: application/json` or a custom header like `X-CSRF-TOKEN` may require preflight because the header/content type exceeds simple request limits.

`PATCH`, `PUT`, and `DELETE` normally require preflight for cross-origin browsers. `OPTIONS` is the method used for preflight, not a promise that application handlers must process every OPTIONS request as business logic.

### 3.2. Mistake: allowing all methods in CORS and thinking method security protects everything

For instance, `allowedMethods("*")` widens the preflight surface. With credentialed requests, Spring handles the wildcard by reflecting the requested method in the response; yet that remains an overly broad CORS policy. Use an allowlist like `GET`, `POST`, `PATCH`… matching the real API. Even if CORS permits PATCH, the user must still hold `item:write`/the right role and pass CSRF guards when cookie authentication is used.

## 4. Allowed headers: which request headers may the frontend send?

`allowedHeaders` specifies request header names the browser is permitted to send in a preflighted cross-origin request. For example, the frontend sends:

```http
PATCH /api/items/42 HTTP/1.1
Origin: https://app.example.com
Content-Type: application/json
X-Request-ID: req-42
X-CSRF-TOKEN: csrf-from-server
Cookie: JSESSIONID=opaque
```

In CORS configuration, allow headers that **the client is permitted to set**, such as `Content-Type`, `X-Request-ID`, `X-CSRF-TOKEN`, and `Authorization` if the frontend uses bearer tokens. Cookies are **not** manually set by JavaScript via `fetch` request headers; cookies are managed by the browser via cookie policy and `credentials`, so **do not add `Cookie` to `allowedHeaders` to “enable cookies”**.

A preflight containing:

```http
Access-Control-Request-Headers: content-type,x-request-id,x-csrf-token
```

needs a matching acceptance in the response:

```http
Access-Control-Allow-Headers: Content-Type, X-Request-ID, X-CSRF-TOKEN
```

Header names match **case-insensitively** per HTTP rules; order is also not a fixed contract. Browsers may lowercase header names in preflight.

### 4.1. Safelisted request headers

Some basic request headers belong to **CORS-safelisted request headers** under specific conditions: `Accept`, `Accept-Language`, `Content-Language`, `Content-Type` with permitted MIME types/values, and certain constrained headers like `Range`. Not every value/format of a header with the same name is safelisted.

For `Content-Type`, the types typically accepted for simple requests are:

- `application/x-www-form-urlencoded`
- `multipart/form-data`
- `text/plain`

`application/json` **is not among those three safelisted types**, so a cross-origin JSON POST usually requires preflight. `Authorization` and custom headers like `X-Trace-ID` also typically trigger preflight.

### 4.2. Do not put response headers in allowed headers to let JS read them

If a controller returns:

```http
HTTP/1.1 200 OK
X-Request-ID: req-42
X-Total-Count: 125
```

adding `X-Total-Count` to `allowedHeaders` **will not** allow browser JavaScript to read this response header. You must declare `exposedHeaders`; the two directions are distinct.

### 4.3. Wildcard `*` in allowed headers

`allowedHeaders("*")` is broader than necessary, allowing preflight for many custom request headers. With credentials, Spring Framework handles wildcards by reflecting the headers requested in preflight, yet you should choose a **finite allowlist** for the headers the application actually uses.

Do not treat `allowedHeaders` as a trusted data validation layer: a non-browser client can still send any header; the backend must validate values, authentication, and business constraints and must never trust client-supplied `X-User-ID`/`X-Tenant-ID`.

## 5. Exposed headers: which response headers may frontend JavaScript read?

Browsers do not let JavaScript read all response headers of a cross-origin fetch merely because CORS permits the response body. Some response headers are **CORS-safelisted response headers** and are accessible by default:

```text
Cache-Control
Content-Language
Content-Length
Content-Type
Expires
Last-Modified
Pragma
```

If the frontend needs to read other response headers such as `X-Request-ID`, `X-Total-Count`, `ETag`, or `Content-Disposition`, the server should list them in:

```http
Access-Control-Expose-Headers: X-Request-ID, X-Total-Count
```

Frontend fetch example:

```javascript
const response = await fetch("https://api.example.com/api/items", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

console.log(response.headers.get("Content-Type"));   // safelisted
console.log(response.headers.get("X-Request-ID"));   // needs exposed
console.log(response.headers.get("X-Total-Count"));  // needs exposed
```

The code only illustrates how to read headers; it does not assert that a given response already contains them. `credentials: "include"` does not guarantee cookies are sent; that still depends on cookie scope, SameSite, Secure, browser policy, and CORS.

### 5.1. `exposedHeaders` does NOT control which headers the frontend sends

In contrast to `allowedHeaders`:

- `allowedHeaders("X-Request-ID")`: browser **may send** `X-Request-ID` in requests after preflight.
- `exposedHeaders("X-Request-ID")`: JavaScript **may read** `X-Request-ID` in CORS responses.
- If an API both accepts a client request-id and returns a server request-id, **both** may be needed.
- If a response includes `X-Total-Count` while the frontend never sends that header, you only need to configure `exposedHeaders` for it, not necessarily allowed headers.

### 5.2. `Set-Cookie` is a special case

`Set-Cookie` is a **forbidden response header name** for the Fetch API. JavaScript cannot read the `Set-Cookie` value via `response.headers.get("Set-Cookie")`, **even** if `Set-Cookie` is added to `Access-Control-Expose-Headers`. The browser manages cookies separately. Do not use exposedHeaders to try to retrieve session IDs.

### 5.3. Wildcard `Access-Control-Expose-Headers: *` with credentials

Under the standard CORS model, wildcard `*` for exposed headers has special semantics for requests **without credentials**. For credentialed requests, `*` is not treated as a universal wildcard. Spring Framework documentation notes some browsers support broader behavior when Spring emits the wildcard even with allowCredentials enabled, yet **you should not rely on implementation quirks and compatibility exceptions**.

**Recommendation:** explicitly declare `exposedHeaders(List.of("X-Request-ID","X-Total-Count"))`. Avoid `"*"` so you do not lose track of sensitive response headers.

## 6. Four-axis matrix — quick reference without direction mix-ups

| Action flow | Browser/client header | Server response header | Spring configuration |
|---|---|---|---|
| Frontend wants to call API | `Origin` | `Access-Control-Allow-Origin` | `allowedOrigins` |
| Frontend wants to call PATCH | `Access-Control-Request-Method: PATCH` in preflight | `Access-Control-Allow-Methods` | `allowedMethods` |
| Frontend wants to send `X-CSRF-TOKEN` | `Access-Control-Request-Headers` in preflight | `Access-Control-Allow-Headers` | `allowedHeaders` |
| Frontend wants to read `X-Total-Count` | JavaScript calls `response.headers.get(...)` | `Access-Control-Expose-Headers` | `exposedHeaders` |
| Frontend uses cookie/auth credentials | `credentials: "include"` + browser cookie policy | `Access-Control-Allow-Credentials: true` and specific origin | `allowCredentials(true)` |
| Browser caches preflight | Browser manages cache automatically | `Access-Control-Max-Age` | `maxAge` |

Example business policy:

```text
Origins:
  https://app.example.com
  https://console.example.com

Methods:
  GET, POST, PATCH, DELETE, OPTIONS

Request headers:
  Authorization, Content-Type, X-CSRF-TOKEN, X-Request-ID

Exposed response headers:
  X-Request-ID, X-Total-Count

Credentials: true
Preflight max age: 1800 seconds
Scope: /api/**
```

Note that `allowCredentials(true)` should only be enabled when the frontend genuinely requires browser credentials. If an API is bearer-only for an SPA explicitly attaching an Authorization header, analyze whether credential mode or any cookies are actually involved. `Authorization` is a request header that usually needs `allowedHeaders` during preflight, yet having `Authorization` does not mean credentialed CORS must be enabled in every scenario.

## 7. Preflight and actual request: complete two-phase flow

### 7.1. Frontend wants to PATCH JSON

JavaScript at `https://app.example.com` calls API `https://api.example.com`:

```javascript
// csrfToken issued by the application from a trusted source, bound to the current session.
const response = await fetch("https://api.example.com/api/items/42", {
  method: "PATCH",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": "req-42",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ label: "Updated" })
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
console.log(response.headers.get("X-Request-ID"));
```

Assuming the browser allows cookies for `api.example.com`, the endpoint authenticates via session, and Spring Security has CSRF protection enabled. The token in code must come from a trusted bootstrap/form flow; never hardcode it or fetch it from an attacker origin.

### 7.2. Browser sends `OPTIONS` preflight

```http
OPTIONS /api/items/42 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-request-id,x-csrf-token
```

**Preflight typically carries no session cookies.** If the authentication/authorization layer runs before CORS and requires a logged-in user for `OPTIONS`, the server may return 401/403 before CORS is processed, preventing the browser from sending the actual request. Spring Security recommends **processing CORS before** security filters requiring credentials.

### 7.3. Server returns preflight policy

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, X-Request-ID, X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Status may be `200` or `204` depending on implementation; the browser cares about CORS policy and response validity. **No cookies/sessions are needed in preflight**. Access-Control-Max-Age only caches preflight within browser-specific limits; it does not extend sessions or CSRF tokens.

### 7.4. Browser sends actual request

If preflight succeeds, the browser sends the actual request with the method/body/headers requested by the frontend. The response may look like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID, X-Total-Count
Content-Type: application/json
X-Request-ID: req-42
X-Total-Count: 1

{"id":42,"label":"Updated"}
```

If the user lacks sufficient permissions or the CSRF token is wrong, the server can still reject the actual request. **Preflight 200 does not mean the actual request will be 200**. If the actual response is blocked by CORS, the browser may report a network/CORS error in JavaScript even when the server processed the request and returned a real HTTP status; DevTools Network helps distinguish these.

## 8. Credentials: cookies, HTTP authentication, and wildcards

With `fetch(..., {credentials: "include"})`, the browser can send cookies/HTTP authentication to a cross-origin API per cookie policy and authentication state. For JavaScript to receive a credentialed CORS response, the server normally needs:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

**Wrong:**

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browsers reject credentialed CORS responses with wildcard origins. Spring also forbids using `allowedOrigins("*")` with `allowCredentials(true)`. Choose an exact origin/allowlist.

**Also distinguish origin and site**: `https://app.example.com` and `https://api.example.com` are cross-origin (requiring CORS for browser fetch) yet usually same-site under SameSite cookies. Do not automatically set `SameSite=None` just because two subdomains are cross-origin. If frontend and API are genuinely on two different registrable domains, third-party cookie blocking can prevent session cookies from being sent even with `SameSite=None; Secure`.

### 8.1. CORS does not replace CSRF

Browsers can send simple cross-origin requests even when the frontend cannot read the response. When cookies/sessions are automatically attached to requests, the backend still needs a CSRF token or a reviewed equivalent. With Spring Security's default CSRF enabled, POST/PATCH/DELETE normally require a valid token; a CORS allowlist does not prove the user intentionally performed the action.

### 8.2. CORS does not replace authentication or authorization

`curl` or non-browser services can send a forged Origin and arbitrary headers. The API must check JWT/session/password, roles, scopes, owner, tenant, and action. Never use the `Origin` value as proof of login or as a tenant ID.

### 8.3. Cookie is not an allowed request header arbitrarily set by frontend

In browser `fetch`, `Cookie` is a forbidden request header managed by the browser. Configuring `allowedHeaders("Cookie")` does not “enable cookies” for JS; you must configure `credentials`, server `allowCredentials`, cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path`, and browser rules.

## 9. Spring Boot MVC/Security: configuring a concrete policy

Example Spring Boot MVC app, Java 17+, using **Spring Framework `CorsConfiguration`**, `UrlBasedCorsConfigurationSource`, and Spring Security 6.x. Class `CorsSecurityConfig.java`:

```java
package com.example.cors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Allowed origins: exact frontend origins.
        config.setAllowedOrigins(List.of(
            "https://app.example.com",
            "https://console.example.com"
        ));

        // Allowed methods for CORS preflight.
        config.setAllowedMethods(List.of(
            "GET", "POST", "PATCH", "DELETE", "OPTIONS"
        ));

        // Request headers the browser is allowed to send.
        config.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-CSRF-TOKEN",
            "X-Request-ID"
        ));

        // Non-safelisted response headers visible to JavaScript.
        config.setExposedHeaders(List.of(
            "X-Request-ID", "X-Total-Count"
        ));

        // Only enable when browser credentials are necessary.
        config.setAllowCredentials(true);
        config.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // CORS integration is placed before authentication.
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items/**")
                    .authenticated()
                .requestMatchers(HttpMethod.PATCH, "/api/items/**")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
```

**Key line-by-line explanation:**

- `setAllowedOrigins` lists exact frontends. Browsers from `https://evil.example.net` receive no CORS permission to read responses.
- `setAllowedMethods` enables GET/POST/PATCH/DELETE/OPTIONS at the CORS layer; it **does not** guarantee the controller/API implements each method or grants user permission.
- `setAllowedHeaders` allows the request headers the frontend needs. Do not add `Cookie` just to support credentials.
- `setExposedHeaders` lets JavaScript read response headers `X-Request-ID` and `X-Total-Count`; there is no need to expose all headers.
- `setAllowCredentials(true)` adapts the policy for frontends using browser-accepted cookies/sessions; increases the trust placed in allowed origins.
- `setMaxAge(1800L)` limits preflight caching in seconds at the policy level; browsers may cap it lower.
- `registerCorsConfiguration("/api/**", ...)` scopes the policy to the API rather than opening all paths. Specific mappings must match real paths and the filter chain covering requests.
- `.cors(Customizer.withDefaults())` integrates CORS with Spring Security so preflight runs in the proper order. With the `UrlBasedCorsConfigurationSource` bean above, Spring Security has a clear policy source.
- `formLogin` illustrates a session/cookie model. `.csrf(Customizer.withDefaults())` retains the CSRF layer; an actual PATCH request needs a valid CSRF token and the EDITOR role.
- `anyRequest().denyAll()` prevents unprotected endpoints/methods from slipping open; never confuse CORS preflight with actual authorization.

**Additional security note:** With server-rendered form login, you need a trustworthy user store, password hashing, `Secure`/`HttpOnly`/`SameSite` cookies, HTTPS, and session management. The code above **focuses solely on CORS/security policy configuration**; it does not provide a user store or controller and is not a standalone Spring Boot app.

### 9.1. Why is CORS needed before Spring Security?

Preflight carries no session cookies under the normal flow. If an authentication filter forces OPTIONS to authenticate before CORS processing, the browser can receive 401/403 and never send the actual PATCH/POST.

Spring Security integrates CORS with Spring MVC or `CorsConfigurationSource`/`CorsFilter`. With multiple security chains, multiple `CorsConfigurationSource` beans, or custom filters, verify which chain holds the policy and the filter ordering. Do not add multiple separate `CorsFilter` instances that duplicate headers in responses; prefer a single clearly managed configuration source.

### 9.2. Policy should not be broadened simply in response to frontend errors

Do not change `allowedOrigins(List.of("https://app.example.com"))` to `allowedOrigins("*")` in production just because the frontend hit a CORS error. Inspect the actual request Origin, preflight method/headers, credentials, proxy, security chain, and route mapping, and add only the genuinely needed origin/header/method.

## 10. Spring Boot MVC + MockMvc demo integrating CORS

Below is a small project example to test the four axes—**allowed origins/methods/headers/exposed headers**—using tests. Uses **JDK 17+**, Maven, Spring Boot **3.5.7**, and Spring Security 6.x managed by Spring Boot. The `example.com` domains are illustrative placeholders and do not need to exist live when testing with MockMvc. Never use demo credentials in production.

Structure:

```text
cors-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cors/
    │   ├── CorsApplication.java
    │   ├── CorsSecurityConfig.java
    │   └── ItemController.java
    └── test/java/com/example/cors/
        └── CorsSecurityTests.java
```

### 10.1. `pom.xml`

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
    <groupId>com.example</groupId>
    <artifactId>cors-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 10.2. `CorsApplication.java`

```java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
```

### 10.3. `ItemController.java`

```java
package com.example.cors;

import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping
    public ResponseEntity<List<Map<String, Object>>> list() {
        return ResponseEntity.ok()
            .header("X-Request-ID", "req-demo")
            .header("X-Total-Count", "1")
            .body(List.of(Map.of("id", 42, "label", "Notebook")));
    }

    @PatchMapping("/{id}")
    public ResponseEntity<Map<String, Object>> patch(
            @PathVariable long id,
            @RequestBody Map<String, String> body) {
        String label = body.getOrDefault("label", "Unchanged");

        // Demo: only returns a response; does not persist changes.
        return ResponseEntity.ok()
            .header("X-Request-ID", "req-patch")
            .body(Map.of("id", id, "label", label));
    }
}
```

`GET /api/items` returns two response headers `X-Request-ID` and `X-Total-Count` to test exposed headers. `PATCH /api/items/{id}` illustrates JSON/CSRF requests and **does not update a real database**. CORS policy creates no authentication/authorization; the controller runs only after Spring Security permits it.

### 10.4. `CorsSecurityTests.java`

```java
package com.example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
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
    .MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedOriginMethodAndHeadersPassPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PATCH")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-request-id,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void unknownOriginFailsPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://evil.example.net")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PATCH"))
            .andExpect(status().isForbidden());
    }

    @Test
    void forbiddenMethodFailsPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownRequestHeaderFailsPreflight() throws Exception {
        mvc.perform(options("/api/items/42")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "PATCH")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-admin-override"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualGetHasCorsAndExposedHeaders() throws Exception {
        mvc.perform(get("/api/items")
                .with(user("alice"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                "X-Request-ID, X-Total-Count"))
            .andExpect(header().string("X-Request-ID", "req-demo"))
            .andExpect(header().string("X-Total-Count", "1"));
    }

    @Test
    void patchWithUserButNoCsrfIsDenied() throws Exception {
        mvc.perform(patch("/api/items/42")
                .with(user("alice").roles("EDITOR"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType("application/json")
                .content("{\"label\":\"Updated\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void patchWithEditorAndCsrfSucceeds() throws Exception {
        mvc.perform(patch("/api/items/42")
                .with(user("alice").roles("EDITOR"))
                .with(csrf())
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType("application/json")
                .content("{\"label\":\"Updated\"}"))
            .andExpect(status().isOk())
            .andExpect(content().json(
                "{\"id\":42,\"label\":\"Updated\"}"));
    }
}
```

**Reading the test results:**

- PATCH preflight is accepted even without `Cookie` or `@WithMockUser`, because CORS runs in the proper order.
- An unknown origin, disallowed PUT method, or disallowed `X-Admin-Override` header causes preflight rejection.
- Authenticated mock GET receives CORS headers and `Access-Control-Expose-Headers` so the browser can read `X-Request-ID`/`X-Total-Count`.
- PATCH with role EDITOR yet missing a CSRF token still returns 403; roles do not replace CSRF guards.
- PATCH with role EDITOR and a valid mock CSRF token passes the HTTP gate and the controller returns the demo JSON.

The tests use `.with(user(...))` to mock authentication and **do not test passwords/form login**. `.with(csrf())` mocks a CSRF token and **does not simulate browser SameSite or real cookies**. CORS rejection status codes may differ if a custom CORS processor/exception handler is changed; the tests here reflect a typical Spring Boot/Security setup.

Run command:

```bash
mvn test
mvn spring-boot:run
```

The Maven example can initialize its context without a user store because tests use mocked users and focus on CORS; when running a real login flow, you must add a `UserDetailsService`/authentication provider and policy-compliant user/password storage. Illustrative HTTPS domains in headers do not need to exist for MockMvc.

## 11. `@CrossOrigin` and MVC configuration: an alternative

Spring MVC can declare CORS on controllers:

```java
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@RestController
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {RequestMethod.GET, RequestMethod.HEAD},
    allowedHeaders = {"Authorization", "Content-Type"},
    exposedHeaders = {"X-Request-ID", "X-Total-Count"},
    allowCredentials = "true",
    maxAge = 1800
)
public class ExampleCrossOriginController {

    @GetMapping("/api/example")
    public String example() {
        return "ok";
    }
}
```

**Scope note:** the annotation on a controller applies to the annotated handler, whereas `CorsConfigurationSource` can define a global path-based policy. If you combine `@CrossOrigin`, `WebMvcConfigurer.addCorsMappings`, and `CorsConfigurationSource`, understand how the framework merges or prioritizes configs to avoid unintended policies. With Spring Security, enable `.cors(...)` properly so preflight passes security filters. A single centralized policy source is generally easier to audit as an API grows.

`@CrossOrigin` can express all four axes, yet you should not scatter annotations across many controllers if their origin/method/header allowlists could drift out of sync. Never use `@CrossOrigin("*")` on credentialed endpoints.

## 12. WebFlux: same CORS semantics, different filter chain APIs

Reactive WebFlux applications use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Configurations **are not interchangeable** with Servlet MVC.

File `ReactiveCorsSecurityConfig.java` for use in a separate WebFlux application:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class ReactiveCorsSecurityConfig {

    @Bean
    CorsConfigurationSource reactiveCorsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(List.of("GET", "PATCH", "OPTIONS"));
        config.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"
        ));
        config.setExposedHeaders(List.of("X-Request-ID"));
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
            CorsConfigurationSource corsSource) {
        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

This is a Spring class requiring Spring Boot WebFlux and Spring Security reactive dependencies. `HttpBasic` in the example only illustrates the authentication pipeline; browsers may auto-send cached Basic credentials, so CSRF remains a concern to evaluate. When integrating session login/SPA, configure WebSession and the token repository appropriately for your architecture.

Notes:

- Choose the **reactive** imports for `CorsConfigurationSource` and `UrlBasedCorsConfigurationSource`.
- The shared `CorsConfiguration` belongs to `org.springframework.web.cors`.
- `CorsWebFilter` or `.cors(...)` integration must process preflight **before authentication**.
- Do not call `block()` or `subscribe()` manually in the security pipeline to “fetch the origin”; CORS processing needs neither.
- Test using `WebTestClient` in a reactive runtime; `MockMvc` tests Servlet only.
- If a project contains both `spring-boot-starter-web` and `spring-boot-starter-webflux`, determine which web runtime Boot actually activates; do not configure both chains expecting both to guard one request.

## 13. Standalone Java 17: modeling the three preflight conditions

The following example is **plain Java**, requiring no Spring. It models how a policy accepts only origins, methods, and request headers present in the allowlists. `exposedHeaders` **does not affect preflight approval**, because it only governs which response headers JavaScript may read.

File `CorsPolicyDemo.java`:

```java
import java.util.Locale;
import java.util.Set;

public class CorsPolicyDemo {

    private static final Set<String> ORIGINS =
        Set.of("https://app.example.com", "https://console.example.com");

    private static final Set<String> METHODS =
        Set.of("GET", "POST", "PATCH", "DELETE", "OPTIONS");

    private static final Set<String> HEADERS =
        Set.of("content-type", "authorization",
               "x-csrf-token", "x-request-id");

    record Request(String origin, String method, Set<String> headers) {}

    static boolean allowedByCors(Request request) {
        return ORIGINS.contains(request.origin())
            && METHODS.contains(request.method())
            && request.headers().stream().allMatch(header ->
                HEADERS.contains(header.toLowerCase(Locale.ROOT)));
    }

    static void check(String name, Request request) {
        System.out.println(name + ": " + allowedByCors(request));
    }

    public static void main(String[] args) {
        check("Allowed GET",
            new Request("https://app.example.com", "GET", Set.of()));
        check("Allowed PATCH",
            new Request("https://app.example.com", "PATCH",
                Set.of("Content-Type", "X-Request-ID")));
        check("Unknown header",
            new Request("https://app.example.com", "PATCH",
                Set.of("X-Admin-Override")));
        check("Unknown origin",
            new Request("https://evil.example.net", "GET", Set.of()));
    }
}
```

Compile and run (JDK 17+):

```bash
javac CorsPolicyDemo.java
java CorsPolicyDemo
```

Exact standard stdout:

```text
Allowed GET: true
Allowed PATCH: true
Unknown header: false
Unknown origin: false
```

This class **does not implement standard CORS**: it omits safelisted headers/methods, cookies/credentials, preflight cache, `Vary`, CORS response serialization, browser-specific policies, and Spring routing. It only helps recognize the **three input dimensions**. `exposedHeaders` does not appear in `allowedByCors` because it is a **response-header reading permission**, not an input gate.

## 14. Using DevTools and curl to verify

### 14.1. Checking preflight with curl

```bash
curl -i -X OPTIONS https://api.example.com/api/items/42 \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: PATCH' \
  -H 'Access-Control-Request-Headers: content-type,x-request-id,x-csrf-token'
```

This command tests the response shape; replace the illustrative URL with a real environment. Verify:

- `Access-Control-Allow-Origin` matches the exact allowed origin.
- `Access-Control-Allow-Methods` includes PATCH (need not be only PATCH).
- `Access-Control-Allow-Headers` accepts the headers requested by the frontend.
- `Access-Control-Allow-Credentials: true` if using credentials and allowed by policy.
- `Access-Control-Max-Age` and `Vary` are sensible; do not cache responses under the wrong origin.
- No session cookie is needed on preflight; do not treat 401 due to missing cookies as normal for a CORS-enabled policy.

**curl does not enforce SOP/CORS**: curl can read the body even when the server omits `Access-Control-Allow-Origin`. It is useful for inspecting backend HTTP responses, **not as a replacement for browser testing**.

### 14.2. Checking the actual response

In DevTools → Network:

1. Determine which actual `Origin` the request carries (scheme/host/port).
2. Check whether there is an OPTIONS preflight; simple requests may have no preflight.
3. Inspect `Access-Control-Request-Method` and `Access-Control-Request-Headers` on OPTIONS.
4. Read the preflight response: ACAO, ACAM, ACAH, ACAC, Max-Age.
5. Read the actual response: ACAO, ACAC, `Access-Control-Expose-Headers`, and the response headers to be read.
6. Check whether cookies are actually sent (credentials/include + cookie policy); do not confuse CORS with SameSite.
7. Check security status codes (401/403), CSRF token, role/permission, and whether the route exists.
8. Check whether a reverse proxy/gateway strips or overwrites CORS headers; test under production-like HTTPS.

**A CORS error in the console is not always the root cause.** A preflight returning 401 due to security ordering, a login redirect, a 500 error lacking CORS headers, browser-blocked cookies, or a misconfigured proxy can all appear as CORS/network failures on the frontend.

## 15. Typical configuration mistakes and how to fix them

| Mistake | Symptom | Fix |
|---|---|---|
| Using `allowedOrigins("*")` with `allowCredentials(true)` | Browser blocks credentialed response; Spring may reject config | Exact origin allowlist |
| Adding only `allowedHeaders` for JS to read a response header | `response.headers.get("X-Total-Count")` returns null | Add corresponding `exposedHeaders` |
| Adding only `exposedHeaders` to send a custom header | PATCH/JSON preflight fails | Add `allowedHeaders` for requests |
| Omitting PATCH from `allowedMethods` | Preflight reports disallowed method | Add exact method if valid in API |
| Origin missing/wrong port/scheme | ACAO mismatches or is absent | Configure exact actual origin |
| OPTIONS preflight requires login | 401/403 before actual request | Integrate CORS before security |
| Sending cookies while configuring only allowedOrigins | JavaScript cannot access credentialed response | allowCredentials and exact origin, plus cookie policy |
| Adding `Cookie` to allowedHeaders to “enable cookies” | No change in behavior | `credentials`/SameSite/Secure/Domain/Path |
| Overly broad CORS, including wildcard patterns | Untrusted origins can read responses | Restrict origins, review subdomains |
| Wrong `Vary` through CDN/cache | One origin's ACAO response served to another origin | Cache-aware headers, Spring CORS processor/proxy |
| Believing CORS blocks every attacker | Non-browser clients still call API | Authentication, authorization, CSRF |
| Response has `Set-Cookie` yet JS cannot read it | `response.headers.get("Set-Cookie")` is null | Managed by browser; never expose cookies |
| Missing allowed Request Header `Authorization` | Bearer fetch preflight rejected | Declare Authorization in allowedHeaders |
| `exposedHeaders("*")` for credentialed requests | Differs across browsers, unreliable | List finite exposed headers |
| CORS policy allows POST while CSRF protects POST | Preflight passes, POST 403 | Send valid CSRF token; do not disable guard |
| Mixing `@CrossOrigin` with global config skews rules | Unexpected CORS results | Single intentional policy, test paths/chains |

### 15.1. Diagnosing in order

1. Is it genuinely cross-origin (scheme, host, port)?
2. Does the browser send preflight? Which method and request headers trigger it?
3. Is the origin in the allowlist? Does the path match the CORS config?
4. Do allowed methods and allowed headers satisfy the preflight?
5. If credentialed, are exact ACAO + ACAC and browser cookie policy aligned?
6. Does the actual response have CORS headers, including on error responses?
7. If reading response headers, are `exposedHeaders` declared?
8. Are authentication/authorization/CSRF and controller mappings blocking the actual request?
9. Is a gateway, CDN, or proxy injecting, caching, or stripping CORS headers?
10. Test in a real browser alongside curl/MockMvc; never draw conclusions from a single console message.

## 16. CORS and other protection layers

### 16.1. CORS vs CSRF

CORS decides whether a JavaScript origin may access a response and pass preflight when needed. CSRF occurs when the browser automatically sends credentials, tricking the server into honoring an unintended request. **A request may be blocked from JS reading the response while still mutating server state**, so CSRF protection is needed for cookie/session apps.

### 16.2. CORS vs authentication and authorization

- A CORS allowlist does not prove the user is Alice, nor does it prove a valid token.
- `hasRole("ADMIN")` and `hasAuthority("item:read")` do not replace a CORS policy.
- Tenant/owner/state checks are required in services when APIs operate on multi-owner resources.
- If authenticated yet lacking scope, the browser may see 403 when CORS responses are properly presented.
- Non-browser API clients do not undergo browser CORS enforcement; backend security must stand on its own.

### 16.3. CORS vs CSP/SOP

SOP is the browser's origin isolation policy. CORS is a mechanism **relaxing** certain cross-origin response-reading restrictions per server-granted permission. CSP (especially `connect-src`) can restrict which destinations the frontend itself may connect to; CSP on the frontend page does not replace CORS on the API.

### 16.4. CORS vs SameSite

CORS is based on **origin**; SameSite cookies are based on **site** (schemeful registrable domain). Two subdomains can be same-site and cross-origin, so the frontend may need CORS while `SameSite=Lax` cookies are still sent under same-site conditions. Conversely, a cross-site frontend with `SameSite=None; Secure` can still face third-party cookie blocking.

## 17. Pre-production checklist

- [ ] Specify exact frontend origins with scheme/host/port; avoid unvalidated domain strings.
- [ ] Use an exact allowlist for `allowedOrigins`; if using patterns, audit subdomains, tenants, and takeover risks.
- [ ] `allowedMethods` contains only genuinely needed methods; do not open wildcards out of habit.
- [ ] `allowedHeaders` contains only request headers needed by the frontend (Content-Type, Authorization, CSRF, request-id...).
- [ ] `exposedHeaders` contains only response headers JavaScript must read (X-Request-ID, X-Total-Count...).
- [ ] With credentials, origins must be specific, `allowCredentials(true)` justified, and cookie policy verified.
- [ ] Preflight is processed before authentication; do not require cookies/sessions on OPTIONS.
- [ ] API still validates JWT/session/password, checks roles/authorities, and guards resources.
- [ ] Unsafe requests have proper CSRF defenses if the browser auto-sends credentials.
- [ ] `Set-Cookie` is never expected to be JS-readable even if exposed.
- [ ] `Vary: Origin` and cache headers are preserved across gateways/CDNs, including preflight conditions.
- [ ] Positive/negative tests cover origins, methods, headers, exposed response headers, and credentials.
- [ ] Test both local development ports and production HTTPS; never blindly relax policy on CORS errors.
- [ ] Distinguish MockMvc/WebTestClient/curl from **real browser behavior**.
- [ ] All broad exceptions are documented, reviewed, and assigned an owner.

## 18. Self-check

**Question 1:** The frontend wants to read `X-Total-Count` in the response. Is adding `X-Total-Count` to `allowedHeaders` enough?

**Answer:** No. `allowedHeaders` applies only to headers sent by the client. You must add `X-Total-Count` to `exposedHeaders` and ensure the API actually returns that header.

**Question 2:** The API allows `https://app.example.com`, while the browser sends `Origin: http://app.example.com`. Do the two origins match?

**Answer:** No; the scheme differs (`http` vs `https`).

**Question 3:** Preflight returns 200 with `Access-Control-Allow-Methods: PATCH`. Is the actual PATCH guaranteed to succeed?

**Answer:** No. The handler might be missing, the user might lack permission, the CSRF token might be wrong, or the payload might be invalid. CORS does not grant permissions.

**Question 4:** The frontend uses cookie authentication. Can the server return `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true`?

**Answer:** No. Credentialed responses require a specific allowed origin; wildcard origin is rejected by browsers.

**Question 5:** OPTIONS preflight has no `JSESSIONID` and Spring Security returns 401. Should the user be prompted to log in again on preflight?

**Answer:** No. CORS must be processed before authentication with properly configured `CorsConfigurationSource` and `.cors(...)`; preflight is not an authenticated business request.

**Question 6:** Can `exposedHeaders` be used to let JavaScript read `Set-Cookie`?

**Answer:** No. `Set-Cookie` is a forbidden response header for Fetch; the browser manages cookies separately.

## 19. Official references

- [Spring Framework – CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html).
- [Spring Framework – CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html).
- [Spring Security – Servlet CORS integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security – Reactive CORS integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- [MDN – Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- [MDN – Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers).
- [MDN – Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers).
- [MDN – Access-Control-Allow-Methods](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Methods).

**Remember:** `allowedOrigins` = **which frontend origins** may read responses; `allowedMethods` = **which HTTP methods** are accepted in CORS preflight; `allowedHeaders` = **which request headers the frontend may send**; `exposedHeaders` = **which response headers the frontend may read**. With cookies/auth credentials, exact origins and an appropriate policy are required. CORS must be handled before Spring Security authentication in the preflight flow, yet **never replaces authentication, authorization, CSRF, TLS, or server-side object-level permissions**.