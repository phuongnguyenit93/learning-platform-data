# Configuring CORS with WebMvcConfigurer or WebFluxConfigurer in Spring Boot

## 1. What problem does CORS solve?

A frontend page running at `http://localhost:5173` calls a Spring Boot API at `http://localhost:8080/api/ping`. The browser can send requests to another host/port, yet the **same-origin policy** prevents JavaScript from reading a response from another origin without proper permission from the server.

**CORS (Cross-Origin Resource Sharing)** is a mechanism based on **HTTP request/response headers** letting a server declare which origins, methods, and headers a browser may use in cross-origin requests. In Spring Boot, the standard ways to configure global CORS are:

- **Spring MVC/Servlet**: implement `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` and override `addCorsMappings(CorsRegistry)`.
- **Spring WebFlux/Reactive**: implement `org.springframework.web.reactive.config.WebFluxConfigurer` and override `addCorsMappings(CorsRegistry)`.

Both APIs serve a similar purpose, yet they belong to **different packages, different web runtimes, and different `HandlerMapping`s**. Never pick an API just because you see "Web" in the name.

This lesson belongs to **Proxy and CORS**, so beyond Java configuration, we also distinguish **CORS at the backend, reverse proxy, API gateway, CDN, and frontend dev proxy**, and explain how to inspect the final response the browser actually sees.

Goals:
1. Understand `Origin`, `OPTIONS` preflight, actual requests, `Access-Control-*` headers, and `Vary`.
2. Write global CORS mappings scoped strictly to `/api/**` with explicit origins.
3. Run two Spring Boot Java 17+ projects—one MVC and one WebFlux—and test both with `curl` and a browser.
4. Use `allowedOrigins`, `allowedOriginPatterns`, `allowedMethods`, `allowedHeaders`, `exposedHeaders`, `allowCredentials`, and `maxAge` accurately.
5. Avoid wildcard + credentials, confusing CORS with auth/CSRF, Security returning 401/403 before preflight, and proxies duplicating headers.
6. Choose where CORS should be handled when running behind a reverse proxy or gateway.

> **Practice versions:** The two separate projects use **Java 17+ and Spring Boot 3.5.x**. MVC uses the `spring-boot-starter-web` starter, and WebFlux uses `spring-boot-starter-webflux`. When creating a Boot 4.x project, the corresponding MVC starter is `spring-boot-starter-webmvc`. The CORS APIs and testing techniques apply to Spring Framework 6.2+/7.x wherever those features are supported. The runnable examples **do not add Spring Security**; Security integration has its own dedicated section.

## 2. An "Origin" is not a full URL

A browser origin is defined by **scheme + host + port**. Path, query, and fragment are not part of the origin.

Examples:

| Open page | API called | Same origin? |
|---|---|---|
| `http://localhost:5173` | `http://localhost:5173/api/ping` | Yes |
| `http://localhost:5173` | `http://localhost:8080/api/ping` | No, different port |
| `https://shop.example.com` | `https://api.example.com/items` | No, different hostname |
| `https://example.com` | `http://example.com/api` | No, different scheme |
| `https://example.com` | `https://example.com:443/api` | Same origin, because 443 is the default HTTPS port |
| `https://example.com` | `https://example.com:8443/api` | No, different port |

The browser adds the `Origin` header for CORS requests when appropriate, for example:

~~~http
Origin: http://localhost:5173
~~~

**Never include paths** in `allowedOrigins`:

~~~text
WRONG: http://localhost:5173/dashboard
RIGHT: http://localhost:5173
~~~

`/dashboard` is a frontend route path; it is not part of the origin. Do not add trailing slashes arbitrarily to origin strings. With HTTPS in production, `http://...` and `https://...` are two distinct origins. `file://` URLs or sandboxed contexts may send `Origin: null`; do not arbitrarily allowlist `null`, as that risks admitting unwanted sources.

CORS relies on **browser enforcement** to restrict JavaScript from reading responses. Scripts using `curl`, Postman, or server-to-server HTTP clients are not governed by browser same-origin policy in the same way. The server must still authenticate and authorize every client; **CORS is not a firewall blocking HTTP requests from unknown origins**.

## 3. How a browser processes a CORS request

### 3.1. Actual requests without preflight

A simple `GET` request can be sent directly:

~~~http
GET /api/ping HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

If the URL/handler is configured to allow the origin, the response may be:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"status":"ok"}
~~~

The browser checks `Access-Control-Allow-Origin`. If it matches the caller's origin and credential mode, JavaScript can read the response. If missing or mismatched, the browser **withholds the response from JavaScript**, even if the server executed the logic and returned HTTP 200 at the network layer.

Therefore, "seeing 200 in the Network tab" **does not mean CORS succeeded**. Check the console, CORS response headers, and whether JavaScript actually received the response.

### 3.2. `OPTIONS` preflight

A `POST` request sending JSON (`application/json`) or a custom header such as `Authorization` normally requires a **preflight**:

~~~http
OPTIONS /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Spring's CORS processor can respond:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

These are **illustrative headers**, not a guarantee of byte-for-byte status codes, ordering, spacing, or casing across every server. Preflight asks whether the browser is **permitted to send** an actual request with that method and headers; it is **not** the business operation itself.

Once preflight succeeds, the browser sends the actual request:

~~~http
POST /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Content-Type: application/json

{"text":"hello"}
~~~

The CORS processor checks the request, adds CORS response headers, and the controller handles the JSON body. The response can contain:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Content-Type: application/json

{"echo":"hello"}
~~~

**Note:** `allowedMethods("GET", "POST")` declares the **actual HTTP methods** the browser may use. You do not have to add `OPTIONS` to `allowedMethods` just to answer preflight; Spring's CORS processor handles `OPTIONS` preflight automatically for matching mappings.

### 3.3. "Simple requests" do not equal safety

Requests satisfying CORS-safelisted method, header, and `Content-Type` criteria can bypass preflight. Yet **skipping preflight** does not mean a user is authorized to invoke the endpoint, nor does it mean the request is immune to CSRF. Browsers can still send certain cross-origin requests and only block JavaScript from reading the response afterward.

Preflight results can also be **cached separately** by the browser according to `Access-Control-Max-Age`. When changing policies, an existing browser may not send a new `OPTIONS` request due to its preflight cache; test in a clean browser session or adjust cache duration in test environments.

## 4. CORS headers you must understand accurately

| Header | Direction | Role |
|---|---|---|
| `Origin` | Request | Origin of the requesting client code |
| `Access-Control-Request-Method` | Preflight request | Actual HTTP method the client intends to use |
| `Access-Control-Request-Headers` | Preflight request | Non-safelisted request header names the client will send |
| `Access-Control-Allow-Origin` | Response | Origin allowed to read the response, or `*` when valid |
| `Access-Control-Allow-Methods` | Preflight response | Allowed actual methods |
| `Access-Control-Allow-Headers` | Preflight response | Request headers allowed to be sent |
| `Access-Control-Allow-Credentials` | Response | Allows browser to expose a credentialed response when client policy also matches |
| `Access-Control-Expose-Headers` | Actual response | Response headers beyond CORS-safelisted headers that JS may read |
| `Access-Control-Max-Age` | Preflight response | Duration the browser may cache the preflight outcome |
| `Vary: Origin` | Response | Helps caches distinguish responses depending on `Origin` |
| `Vary: Access-Control-Request-Method` | Response | Useful when preflight outcome depends on method |
| `Vary: Access-Control-Request-Headers` | Response | Useful when preflight outcome depends on headers |

`Access-Control-Max-Age` is **not** a TTL for API JSON responses; it is the preflight cache duration. HTTP `Cache-Control` still governs representation caching. With a CDN or shared cache, `Vary` must be preserved whenever CORS headers vary by `Origin` so a cached response for origin A is never served with headers for origin B.

## 5. Why choose `WebMvcConfigurer` vs. `WebFluxConfigurer`?

| Use case | Configuration API | Key package |
|---|---|---|
| Spring MVC / Servlet | `WebMvcConfigurer` | `org.springframework.web.servlet.config.annotation` |
| Spring WebFlux / Reactive | `WebFluxConfigurer` | `org.springframework.web.reactive.config` |
| Only one controller needs a custom rule | `@CrossOrigin` | `org.springframework.web.bind.annotation` |
| CORS before filter chain or special needs | `CorsFilter` (MVC), `CorsWebFilter` (WebFlux) | `org.springframework.web.filter` / `org.springframework.web.cors.reactive` |
| Gateway acting as reverse proxy for multiple services | Configure CORS on the gateway properly | Do not assume a backend Configurer handles gateway routes |

Spring MVC uses `DispatcherServlet` and MVC `HandlerMapping`s. WebFlux uses reactive `HandlerMapping`s and `WebHandler`. Both provide `addCorsMappings`, yet each affects only its own stack.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot usually selects **SERVLET/MVC**. Importing `WebClient` does not switch the whole app to WebFlux. To learn cleanly, run two separate projects rather than mixing both starters.

**Spring Boot autoconfiguration:** you do not need `@EnableWebMvc` or `@EnableWebFlux` just to add CORS mappings. Those annotations hand many MVC/WebFlux configuration choices back to your app and can alter Boot-managed defaults. A `@Configuration` class implementing the configurer is the right choice for this lesson.

## 6. `CorsRegistration` methods in `addCorsMappings`

Example applied to URL pattern `/api/**`:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins("http://localhost:5173")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
        .exposedHeaders("X-Request-Id")
        .allowCredentials(false)
        .maxAge(1800);
~~~

Explanation:

- `addMapping("/api/**")`: restricts which URL paths receive the **global CORS rule**. This pattern does not create endpoints, change controller routing, or force APIs to start with `/api` if controllers live elsewhere.
- `allowedOrigins(...)`: list of **exact allowed origins**, including scheme/host/port. Multiple verified origins can be listed, such as a localhost dev frontend and a production frontend.
- `allowedMethods(...)`: actual methods browsers may use. If an API exposes `PUT`/`DELETE`, add them deliberately after testing.
- `allowedHeaders(...)`: request headers clients may request during preflight, such as `Content-Type`, `Authorization`, `X-Request-Id`. They are **not** response headers.
- `exposedHeaders(...)`: response headers JavaScript may access via `response.headers.get(...)` beyond safelisted response headers. It does not grant sending request headers.
- `allowCredentials(false)`: this demo does not use cross-origin cookies or HTTP credentials. Global CORS defaults to credentials off as well; writing it explicitly clarifies intent.
- `maxAge(1800)`: duration in **seconds** for preflight caching—30 minutes here. Browsers may enforce their own upper caps.
- `/**` is path matching, not a wildcard meaning "every origin."

### Default global CORS is overly broad if left unconfigured

Per Spring Framework, a default global CORS mapping allows all origins and headers, with `GET`/`HEAD`/`POST` methods, and credentials disabled. Thus never write just `registry.addMapping("/**")` in a production API assuming methods and domains are safely locked down. Declare a policy matching your actual API contract.

## 7. Lab A — Spring Boot MVC with `WebMvcConfigurer`

Create a project via **Spring Initializr**: Spring Boot **3.5.x**, Java 17+, Gradle, **Spring Web** dependency. Initializr includes the Gradle Wrapper. If the project already has the Boot plugin and dependency management, declare the starter as:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

This is a **dependency fragment**, not a full build file. With Boot 4.x, choose `spring-boot-starter-webmvc`.

Create **one Java file** at `src/main/java/demo/corsmvc/CorsMvcApplication.java`:

~~~java
package demo.corsmvc;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class CorsMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsMvcApplication.class, args);
    }
}

@Configuration
class MvcCorsConfiguration implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(false)
                .maxAge(1800);
    }
}

@RestController
class MvcDemoController {
    public record EchoRequest(String text) { }

    @GetMapping("/api/ping")
    public ResponseEntity<Map<String, String>> ping() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-42")
                .body(Map.of("status", "ok"));
    }

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> echo(@RequestBody EchoRequest input) {
        return Map.of("echo", input.text());
    }
}
~~~

`MvcCorsConfiguration` and `MvcDemoController` are intentionally **package-private top-level classes** in the same source file; Java allows one `public` class and any number of non-public classes per file. Spring Boot component scanning from package `demo.corsmvc` picks up both annotated beans. No extra Java files are needed.

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
~~~

Run from the project root:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

The application exposes two APIs:
- `GET /api/ping` returns `{"status":"ok"}` and response header `X-Request-Id: demo-42`.
- `POST /api/echo` accepts JSON `{"text":"hello"}` and returns `{"echo":"hello"}`.

### 7.1. Testing an actual `GET` with a valid `Origin`

~~~bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/ping
~~~

**Expected response body:**

~~~json
{"status":"ok"}
~~~

Response headers to look for:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: X-Request-Id
X-Request-Id: demo-42
Vary: Origin
~~~

The `Vary` header may actually be written as one or multiple field lines, also including `Access-Control-Request-Method` and `Access-Control-Request-Headers`. Byte-for-byte line matching or casing is not required. Because `allowCredentials(false)` is set, `Access-Control-Allow-Credentials: true` should not appear.

### 7.2. Testing `OPTIONS` preflight before a JSON `POST`

~~~bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type' \
  http://localhost:8080/api/echo
~~~

Headers to verify in the allowed preflight response:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
~~~

The HTTP status is typically 200 in this setup; the response body may be empty or vary by framework. `Content-Type` in `allowedHeaders` refers to the permitted request header name, **unrelated** to enabling CORS for the response content type.

### 7.3. Sending the actual `POST`

~~~bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/echo
~~~

**Expected response body:**

~~~json
{"echo":"hello"}
~~~

Note that `curl` **does not perform browser preflight automatically**: the `OPTIONS` and `POST` commands run independently. Browsers decide whether to preflight based on method, headers, credentials, and policy.

### 7.4. Testing a disallowed origin

~~~bash
curl -i \
  -H 'Origin: https://untrusted.example.test' \
  http://localhost:8080/api/ping
~~~

This origin is not on the allowlist. With Spring MVC's default CORS processor, a rejected cross-origin request may return **403 Invalid CORS request**, depending on handler/filter/security/proxy setup. **Do not rely on a single exact status code** to verify security: check whether `Access-Control-Allow-Origin` permits the unknown origin, and test actual browser behavior.

More importantly, **CORS does not replace authentication**. Same-origin requests or server-to-server clients can still reach the controller when allowed by other layers.

## 8. Lab B — Spring Boot WebFlux with `WebFluxConfigurer`

Create a **separate project**, Spring Boot 3.5.x, Java 17+, Gradle, **Spring Reactive Web** dependency. Do not add the MVC starter. Dependency fragment:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Create `src/main/java/demo/corsflux/CorsWebFluxApplication.java`:

~~~java
package demo.corsflux;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class CorsWebFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsWebFluxApplication.class, args);
    }
}

@Configuration
class ReactiveCorsConfiguration implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
                .exposedHeaders("X-Request-Id")
                .allowCredentials(false)
                .maxAge(1800);
    }
}

@RestController
class ReactiveDemoController {
    public record EchoRequest(String text) { }

    @GetMapping("/api/ping")
    public Mono<ResponseEntity<Map<String, String>>> ping() {
        return Mono.just(ResponseEntity.ok()
                .header("X-Request-Id", "demo-42")
                .body(Map.of("status", "ok")));
    }

    @PostMapping(
            path = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<EchoRequest> input) {
        return input.map(body -> Map.of("echo", body.text()));
    }
}
~~~

This code is a complete single-file Java source for the WebFlux project. Both `ReactiveCorsConfiguration` and the controller are scanned by Spring. Notice `CorsRegistry` is imported from **`org.springframework.web.reactive.config.CorsRegistry`**, not the servlet package. The `POST` handler uses `Mono<EchoRequest>` and `Mono<Map<...>>` to reflect reactive programming style. Do not call `block()` inside the controller.

Run `./gradlew bootRun` (or `.\gradlew.bat bootRun` on Windows) from the **WebFlux project**, after stopping the MVC app if both use port 8080.

Use **the exact same three `curl` commands from section 7** to verify:
1. `GET /api/ping` with allowed origin: body `{"status":"ok"}` and CORS headers.
2. `OPTIONS /api/echo` with `POST`, `content-type`: matching preflight headers.
3. `POST` JSON `{"text":"hello"}`: body `{"echo":"hello"}`.

The HTTP headers, statuses, and CORS policy apply identically because the definition matches, even though the runtime differs. Never assume WebFlux "does not need CORS" just because it is non-Servlet: the browser's same-origin policy does not depend on whether the server is reactive or blocking.

## 9. Using `allowedOriginPatterns` when a list of subdomains is needed

If legitimate frontends live across several subdomains, you can use `allowedOriginPatterns(...)`:

~~~java
// Fragment inside addCorsMappings for MVC or WebFlux:
registry.addMapping("/api/**")
        .allowedOriginPatterns("https://*.example.com")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type")
        .allowCredentials(true);
~~~

**Distinction:**
- `allowedOrigins("https://app.example.com")` allows **exactly** one origin.
- `allowedOrigins("*")` allows any origin when credentials are not used. It cannot be combined with `allowCredentials(true)` in Spring Framework.
- `allowedOriginPatterns("https://*.example.com")` matches an origin group by pattern; on a match, Spring echoes back **the specific matched origin** rather than literal `*` in `Access-Control-Allow-Origin`. Thus it works technically with credentials under Spring's mechanism.

However, **syntactically valid does not mean policy-safe**. Wildcard subdomains can accidentally cover third-party-controlled subdomains, user-hosted pages, or weakly secured staging environments. With cookie-based auth, that widens the set of sites able to read user data. Prefer a finite list of explicit origins; use patterns only after assessing subdomain governance and takeover risks.

Never turn `allowedOriginPatterns("*")` into a production policy with credentials: it effectively admits unlimited origins and creates severe risk. If your system needs many dynamic tenant origins, consider a managed allowlist, verified tenant ownership, and secure config updates.

### Common URL input mistakes

- `allowedOrigins("localhost:5173")` missing scheme: invalid origin.
- `allowedOrigins("https://example.com/path")` contains a path: does not match browser `Origin`.
- Allowlisting only `http://localhost:5173` while the frontend runs at `http://127.0.0.1:5173`: different origin.
- Allowlisting `https://app.example.com` while requests come from `https://www.app.example.com`: different hostname.
- Running an HTTPS frontend while allowing only an HTTP origin: different scheme.
- Confusing `*.example.com` with the apex origin `https://example.com`: declare the apex explicitly if needed.

## 10. Credentials, cookies, and `fetch`: three conditions must all hold

In the demo, `allowCredentials(false)` is set because there are no cross-origin session cookies. When a real frontend must send session cookies:

~~~javascript
const response = await fetch("https://api.example.com/me", {
  credentials: "include"
});
const data = await response.json();
~~~

The server needs a compatible policy, for example:

~~~java
// addCorsMappings fragment in the stack's configurer:
registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowedMethods("GET", "POST")
        .allowedHeaders("Content-Type", "X-CSRF-TOKEN")
        .allowCredentials(true);
~~~

For a credentialed CORS request, the browser simultaneously requires:
1. Frontend sends the request with the **matching credential mode**, such as `credentials: "include"` for cross-origin cookie fetches.
2. Server response has **`Access-Control-Allow-Origin` set to the specific origin**, never `*`.
3. Response includes **`Access-Control-Allow-Credentials: true`**.
4. The cookie satisfies **`Domain`, `Path`, `SameSite`, `Secure`, and browser cookie policies**. For cross-site cookies, `SameSite=None; Secure` over HTTPS and third-party cookie restrictions usually apply.
5. The endpoint still enforces auth, authorization, and CSRF policies; CORS governs only whether the browser exposes the response.

**Note that Origin differs from Site.** Two hostnames `app.example.com` and `api.example.com` are **cross-origin** (requiring CORS), yet are typically **same-site** under the schemeful site model if they share scheme and registrable domain. `SameSite` conditions are not identical to CORS conditions.

`Access-Control-Allow-Credentials: true` will not make the browser send cookies if the client omits them or cookie rules block them. Conversely, `credentials:"include"` cannot bypass an unallowlisted origin on the server.

### Bearer tokens and credentials

If the frontend sends `Authorization: Bearer ...`, adding the `Authorization` header usually triggers preflight and requires `allowedHeaders("Authorization")`. CORS does not check token validity. Depending on credential mode and how requests are issued, browser credential and response rules still apply, yet **do not equate "uses `Authorization` header" with "must always set `allowCredentials(true)`."** For token-based APIs without cookies, restricting origins/methods/headers and validating tokens server-side per your design is often sufficient.

## 11. CORS does not replace authentication, authorization, or CSRF

CORS is a browser mechanism governing **reading cross-origin responses**, not a control that forces all HTTP clients to comply. An unprotected delete endpoint can still be called directly with `curl` regardless of CORS config. A malicious page can also trigger certain requests without reading the response; therefore CORS **does not automatically block CSRF**.

For apps using session cookies:
- Protect state-changing endpoints with CSRF protection or equivalent safeguards.
- Enforce backend authentication and authorization on every protected request.
- Allowlist only the origins whose JavaScript should read sensitive responses.
- Never enable credentials for every origin just to "fix a CORS error."
- Never relax Security to `anyRequest().permitAll()` just to resolve a 401 on preflight.

## 12. Spring Security: handle CORS before authorization

When adding Spring Security, `OPTIONS` preflight requests normally **carry no session cookies** like actual requests do; if Security treats preflight as an unauthenticated request before the CORS processor runs, it can return 401/403 and prevent the browser from ever sending the actual `POST`.

### Spring MVC and `SecurityFilterChain`

When CORS rules are declared via `WebMvcConfigurer` and Spring MVC is on the classpath, Spring Security can integrate MVC CORS configuration via `http.cors(...)` provided there are no competing CORS sources. Example **fragment** in a `@Configuration` class using Spring Security 6.5 (Boot 3.5):

~~~java
// Fragment; requires Spring Security dependency and corresponding imports.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        );
    return http.build();
}
~~~

Key imports:
- `org.springframework.security.config.Customizer`
- `org.springframework.security.web.SecurityFilterChain`
- `org.springframework.security.config.annotation.web.builders.HttpSecurity`
- `org.springframework.context.annotation.Bean`

This snippet is **not standalone runnable** and does not turn the section 7 demo API into a public endpoint: it requires real authentication. For cookie/session-based `POST`s, CSRF must still be handled; never disable CSRF carelessly just to test.

### WebFlux and `SecurityWebFilterChain`

WebFlux apps use `ServerHttpSecurity` and `SecurityWebFilterChain`, not Servlet `HttpSecurity`:

~~~java
// Reactive Spring Security fragment; requires imports and bean configuration.
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http.cors(Customizer.withDefaults())
        .authorizeExchange(auth ->
            auth.anyExchange().authenticated()
        )
        .build();
}
~~~

For complex CORS or early filter-level enforcement, WebFlux offers `CorsWebFilter` and `UrlBasedCorsConfigurationSource` from the reactive package; Servlet has `CorsFilter` and the Servlet configuration source. **Never register multiple CORS filters with overlapping responsibilities** without defining who emits or overwrites headers.

### When is a Configurer not enough?

- CORS must run **before the security filter chain**, yet security integration is not picking up mappings.
- The API uses **functional endpoints** or gateway routing outside annotated `HandlerMapping`s.
- Early CORS enforcement is needed in a cross-cutting filter before handler mapping runs.
- Multiple security chains or dynamic per-tenant CORS policies require a dedicated source.

In those cases, consider `CorsConfigurationSource` with `CorsFilter` / `CorsWebFilter` aligned with your Security version. Never solve it by disabling authentication or CSRF.

## 13. Choosing where to handle CORS behind a reverse proxy or gateway

A common architecture:

~~~text
Browser https://app.example.com
       |
       | Origin: https://app.example.com
       v
CDN / reverse proxy / API gateway
       |
       +------> Spring Boot MVC service A
       |
       +------> Spring Boot WebFlux service B
~~~

Two valid approaches depending on architecture:

**Option A — the backend handles CORS itself** via Configurer. The proxy forwards `Origin`, `OPTIONS`, and required headers to the backend and preserves CORS response headers returned by the backend. Good when each service owns its own API and origin policy.

**Option B — the gateway handles CORS centrally.** The gateway answers preflight and attaches CORS headers for browsers. Good when multiple backends share one policy and the gateway controls routing. Under this option, ensure backends do not also emit duplicate or conflicting CORS headers.

Do not assume a backend `WebMvcConfigurer` can handle preflight requests blocked at a CDN/gateway: the request may never reach the backend. Likewise, one service's `WebFluxConfigurer` does not configure an entire separate Spring Cloud Gateway.

### Common proxy mistakes

- Gateway **blocks `OPTIONS`** because it only routes `GET`/`POST` or an auth filter intercepts preflight.
- Reverse proxy adds `Access-Control-Allow-Origin: *` to all responses while the backend returns an explicit origin; browsers see **multiple or conflicting CORS header values**.
- Proxy overwrites `Vary`, causing cached responses from origin A to be served to origin B.
- Host/scheme rewrites make backend origin/security checks disagree with the real public URL.
- Frontend uses a dev proxy such as Vite `/api`; the browser calls the **same-origin dev server** so CORS never appears locally, yet production hits the API domain directly and needs a policy.
- Some endpoints return from the gateway (404/502) while others return 200 from the backend: inconsistent CORS headers cause the browser to report only "CORS error" instead of the underlying HTTP failure.

**Operational rule:** designate **one clear layer owning the CORS policy** per public route. If multiple layers must participate, specify header-merging responsibilities and test the final response at the public endpoint.

## 14. CORS, `Vary`, and HTTP caching

When CORS responses vary `Access-Control-Allow-Origin` by request `Origin`, shared caches must avoid mixing variants:

~~~http
Vary: Origin
~~~

For preflight, `Access-Control-Request-Method` and `Access-Control-Request-Headers` can also affect the response:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Spring's CORS processor usually adds appropriate `Vary` headers; check responses at the gateway/CDN and do not strip them when adding compression or caching rules. **`Vary` does not decide whether a response may be cached.** For user-specific data, use `Cache-Control: private` or `no-store` appropriately—never rely on `Vary: Origin` or `Vary: Cookie` alone for data confidentiality.

Distinguish:
- **`Access-Control-Max-Age`**: browser caching of the *preflight* result.
- **`Cache-Control`**: private/shared HTTP caches deciding whether to store/reuse a response.
- **`Vary`**: request headers used as cache-key discriminators to select the right variant.

If the frontend uses session cookies, personalized responses vary by user even when `Origin` is the same; varying only by origin **does not prevent data leaks** in shared caches. Dedicated HTTP cache policies for user data are mandatory.

## 15. `@CrossOrigin` vs. global CORS configuration

`@CrossOrigin` attaches rules to a controller class or method:

~~~java
// Spring MVC or WebFlux annotated controller fragment.
@CrossOrigin(origins = "https://app.example.com")
@GetMapping("/api/status")
public String status() {
    return "ok";
}
~~~

Pros: rule is easy to read right next to the endpoint. Cons: easy to duplicate across controllers, and policies become scattered.

`WebMvcConfigurer` / `WebFluxConfigurer` is a better place to manage **global policies by URL namespace**, which can be tested centrally.

Spring Framework can **combine global and local CORS configurations**:
- Origin/method/header lists are normally merged additively.
- Single-valued properties such as `allowCredentials` and `maxAge` typically let local override global.
- The combined result can be **broader than intended**, e.g., global allows A, local allows B ⇒ both A and B are permitted on that route.

Thus when a strict allowlist is needed, **do not assume `@CrossOrigin` replaces the global CORS origin list completely**. Check `CorsConfiguration`'s combination rules and test multiple origins. Avoid configuring an overly broad global `/**` and trying to "tighten" individual controllers with annotations, since additive merging can defeat that goal.

## 16. Common errors and troubleshooting

| Symptom | Possible cause | How to verify/fix |
|---|---|---|
| Console reports "No Access-Control-Allow-Origin" | No matching CORS mapping or proxy drops the header | Check `Origin`, URL, path pattern, and final response |
| `OPTIONS` returns 401 | Security filter runs before CORS | Integrate `http.cors` or `CorsWebFilter` for your stack; do not disable auth |
| `OPTIONS` returns 404/405 | Gateway does not route `OPTIONS` or custom handler intercepts it | Check gateway/proxy/router and Spring `HandlerMapping` |
| `OPTIONS` succeeds yet `POST` fails | Actual request auth/CSRF/validation or proxy behavior differs | Inspect `POST` response and logs; do not assume CORS covers everything |
| Browser blocks `GET`, `curl` shows 200 | `curl` does not enforce browser CORS checks | Inspect ACAO/ACAC, DevTools console, and real origin |
| Browser reports wildcard invalid with credentials | `allowCredentials(true)` + `allowedOrigins("*")` or wildcard ACAO | Use finite origins or tightly controlled patterns |
| Works on localhost, fails for frontend | Frontend runs on a different port/scheme/hostname | Compare `Origin` against `allowedOrigins` byte-for-byte and semantically |
| CORS errors occur only in production | Same-origin dev proxy masked the issue; gateway changes routes/headers | Test public production URL through a browser |
| Two `Access-Control-Allow-Origin` headers | Gateway and backend both add CORS headers | Designate one CORS owner and remove duplicate headers |
| `allowedHeaders` has `Authorization` yet JS cannot read `X-Request-Id` | Confused request `allowedHeaders` with response `exposedHeaders` | Add `exposedHeaders("X-Request-Id")` |
| API returns 403 for unknown `Origin` | Spring CORS processor rejected it | Check origin allowlist; do not rush to allow all origins |
| WebFlux app ignores `WebMvcConfigurer` | Wrong Servlet import/configurer used | Use `WebFluxConfigurer` from the reactive package |
| MVC app ignores `WebFluxConfigurer` | Boot chose Servlet/MVC | Use `WebMvcConfigurer` from the MVC package |
| Local `@CrossOrigin` does not "narrow" origins | Global and local origin lists merged | Review `CorsConfiguration.combine` and fix global policy |
| Cross-site cookies not sent | Missing `credentials:"include"`, wrong `SameSite`/`Secure`/`Domain`, or third-party cookie blocking | Inspect DevTools Cookies and HTTPS policy |
| Browser still reports CORS on 500 errors | Error response from proxy/handler lacks CORS headers | Inspect real status and ensure consistent CORS handling on error paths |
| Backend updated yet CDN unchanged | `OPTIONS`/ACAO handled or cached at CDN | Inspect gateway config and invalidate cache per policy |
| `Origin: null` causes request failure | Browser came from sandbox/file origin outside allowlist | Serve frontend from a valid HTTP origin; do not blindly allowlist `null` |

### Concise debugging sequence

1. Record the **exact frontend origin** (scheme/host/port).
2. Record the **request URL**, method, and headers (especially `Content-Type`, `Authorization`, custom headers).
3. Check whether an `OPTIONS` preflight ran; if so, record `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
4. Identify which layer returned the response first (browser cache, CDN, gateway, Spring).
5. Inspect CORS rules: `addMapping`, origins, methods, `allowedHeaders`, credentials.
6. If Security is present, check CORS and Security/CSRF ordering.
7. Inspect actual response `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, and `Vary`.
8. Test in a real browser rather than concluding from `curl` alone.
9. Fix the right layer and test both allowed and disallowed origins.

## 17. Automated testing with `MockMvc` and `WebTestClient`

You do not need to launch a browser for every case; server-side statuses and headers can be tested automatically.

### 17.1. MVC — `MockMvc`

This is a **test fragment** inside an MVC project with `spring-boot-starter-test` and Spring Boot test infrastructure:

~~~java
// Inside a @SpringBootTest + @AutoConfigureMockMvc test class
// with @Autowired MockMvc mvc; standard Spring Test imports.
mvc.perform(options("/api/echo")
        .header("Origin", "http://localhost:5173")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type"))
   .andExpect(status().isOk())
   .andExpect(header().string(
       "Access-Control-Allow-Origin", "http://localhost:5173"));
~~~

Because this is a fragment, it does not compile standalone via `javac`. In a Boot 3.5 project, `MockMvc` and matchers are pulled in by `spring-boot-starter-test`. The full hands-on app in section 7 remains self-contained without this test fragment.

### 17.2. WebFlux — `WebTestClient`

This is a **test fragment** inside a WebFlux project with `spring-boot-starter-test`, injecting a properly configured `WebTestClient`:

~~~java
// Inside an integration test with configured WebTestClient client:
client.options()
      .uri("/api/echo")
      .header("Origin", "http://localhost:5173")
      .header("Access-Control-Request-Method", "POST")
      .header("Access-Control-Request-Headers", "content-type")
      .exchange()
      .expectStatus().isOk()
      .expectHeader()
      .valueEquals("Access-Control-Allow-Origin",
                   "http://localhost:5173");
~~~

`WebTestClient` tests reactive handlers without manually scripting an HTTP client. Still, actual **browser** outcomes also depend on caching, cookie policy, browser-generated `Origin`, and proxies/CDNs, so integration tests do not replace end-to-end verification.

### Recommended CORS test matrix

| Case | Origin | Method/Header | Expectation |
|---|---|---|---|
| Valid `GET` | `http://localhost:5173` | `GET` | CORS allows it, accurate body |
| Valid JSON `POST` | `http://localhost:5173` | `OPTIONS` → `POST`; `content-type` | Preflight allows it; `POST` reaches controller |
| Other origin | `https://untrusted.example.test` | `GET` | Browser cannot read as an allowed origin |
| Disallowed method | `http://localhost:5173` | Preflight `DELETE` | Not advertised as allowing `DELETE` |
| Disallowed header | `http://localhost:5173` | Preflight `X-Forbidden` | Not advertised as allowing that header |
| No `Origin` | Omitted | `GET` | Same-origin/server-to-server request still obeys auth/routing |
| Credentials with wildcard | Selected origin | `credentials:"include"` | Never emits `Access-Control-Allow-Origin: *` |
| Security enabled | Valid origin | `OPTIONS` / `POST` | Preflight runs before auth; `POST` enforces valid auth/CSRF |
| Behind gateway | Valid and invalid origins | `OPTIONS` and actual | Consistent single policy, no duplicate CORS headers |

## 18. Summary of a safe implementation workflow

A reliable CORS policy starts from **where real frontend requests originate**, not from console error messages. If the frontend is at `https://app.example.com` and the API is at `https://api.example.com`, write an explicit policy for `/api/**` covering only the origins, methods, and headers actually used. Then:
- Choose **`WebMvcConfigurer`** if Boot runs Servlet/MVC, or **`WebFluxConfigurer`** if Boot runs WebFlux.
- Place the configurer in a component-scanned package without `@EnableWebMvc`/`@EnableWebFlux`.
- Enable credentials only when cross-origin cookies/credentials are genuinely required; allowlist trusted origins explicitly.
- Ensure CORS runs **before or properly integrated with Security**, without weakening authorization or CSRF.
- Behind a gateway/proxy, establish clearly who owns CORS and who handles `OPTIONS`.
- Monitor `Access-Control-Allow-Origin`, `Vary`, `OPTIONS`/`POST` logs, caching policies, and browser behavior.
- Verify using **preflight + actual request pairs** in both development and public production endpoints.

## 19. Review questions

**Q1.** A page at `http://localhost:5173` calls `http://localhost:8080/api/ping`. Why is CORS needed?

**Answer:** Same host yet different ports mean different origins; the browser prevents JavaScript from reading the response without matching CORS response headers.

**Q2.** Both MVC and WebFlux have `addCorsMappings`; can you use `WebMvcConfigurer` for WebFlux?

**Answer:** No. You must implement the configurer and `CorsRegistry` matching your stack: MVC uses `org.springframework.web.servlet.config.annotation`; WebFlux uses `org.springframework.web.reactive.config`.

**Q3.** Given `allowedMethods("GET","POST")`, do you also have to add `"OPTIONS"` to answer preflight?

**Answer:** Not required. `allowedMethods` lists the actual methods; the CORS processor handles `OPTIONS` preflight for matching routes automatically.

**Q4.** Does `allowedHeaders("Authorization")` automatically let JavaScript read the response header `X-Request-Id`?

**Answer:** No. `allowedHeaders` governs request headers; to let JS read a non-safelisted response header, configure `exposedHeaders("X-Request-Id")`.

**Q5.** Can you use `allowedOrigins("*").allowCredentials(true)`?

**Answer:** No. Spring Framework rejects wildcard all-origins via `allowedOrigins("*")` when credentials are true. Use an explicit origin allowlist; use `allowedOriginPatterns` only when truly needed and tightly scoped.

**Q6.** Why does CORS preflight return 401 after enabling Spring Security while `curl GET` without `Origin` still works?

**Answer:** Preflight lacks session cookies and may be intercepted by Security before CORS runs; integrate CORS properly ahead of Security. A `GET` without `Origin` is not a CORS preflight.

**Q7.** If a proxy returns `Access-Control-Allow-Origin` and the backend also returns that header, what happens?

**Answer:** The response can contain duplicate/conflicting CORS headers, causing browsers to reject it; pick one consistent owner or merge under strict rules.

**Q8.** Does CORS protect an API from `curl` calling a resource-deletion endpoint?

**Answer:** No. CORS is a browser-enforced read policy; authentication, authorization, and CSRF where applicable must be enforced independently on the backend.

**Q9.** Does `maxAge(1800)` mean the browser caches API JSON data for 30 minutes?

**Answer:** No. It governs preflight cache duration, not `Cache-Control` of the actual JSON response.

**Q10.** Should you skip production CORS configuration just because localhost works through a dev proxy?

**Answer:** No. A dev proxy can make browser requests same-origin and mask cross-origin production behavior; test the final public URL with real `Origin` headers and gateway/proxy layers.

### Extension exercise

In the MVC or WebFlux project from section 7/8, add `PUT /api/echo`, **without** adding `PUT` to `allowedMethods`. Send an `OPTIONS` preflight with `Access-Control-Request-Method: PUT` and record the result. Next, add `PUT` to the allowlist and retry. Then change the frontend `Origin` to `http://localhost:4173` and observe requests being rejected until the allowlist is updated. Finally, add an `X-Server-Version` response header and test `response.headers.get("X-Server-Version")` in the browser before and after adding `exposedHeaders("X-Server-Version")`.

## 20. Official documentation

- [Spring Framework 6.2 — CORS for Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html)
- [Spring Framework 6.2 — CORS for Spring WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework — WebMvcConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework — WebFluxConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html)
- [Spring Security — Servlet CORS integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — Reactive CORS integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html)
- [Spring Boot — MVC customization](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — WebFlux customization](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [WHATWG Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol)

**Conclusion:** `WebMvcConfigurer.addCorsMappings` and `WebFluxConfigurer.addCorsMappings` are the two CORS configuration points **matching their respective web stacks**. A sound policy matches actual origins, methods, and headers, controls credentials, processes preflight before auth when needed, and stays consistent across reverse proxies and CDNs. CORS lets browsers read responses from designated origins; **it does not replace API security**.