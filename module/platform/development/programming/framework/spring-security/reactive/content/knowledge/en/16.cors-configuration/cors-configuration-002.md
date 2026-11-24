# Simple Requests, Preflight Requests, and the OPTIONS Method in CORS

## 1. Context and Goals

In a **Spring Security reactive / Spring WebFlux** application, a frontend at `http://localhost:5173` calling an API at `http://localhost:8080` commonly involves **CORS — Cross-Origin Resource Sharing**. Some requests are sent directly by the browser; others cause the browser to **automatically send an HTTP OPTIONS request first** to ask the server about the origin, method, and headers the actual request intends to use.

A common misconception: **CORS is a browser policy controlling whether JavaScript from another origin may read a response**, not a login, authorization, or CSRF mechanism. An accepted preflight **does not mean** the actual request is authenticated, authorized, or exempt from CSRF.

After this lesson, you will be able to:

1. Distinguish **origin**, **cross-origin**, **cross-site**, and same-origin; recognize differences in scheme, host, or port.
2. Classify a **CORS simple request** (the popular documentation term; in Fetch, a request using safelisted methods/headers) versus a request **requiring preflight**.
3. Explain an `OPTIONS` request with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`, along with the corresponding response headers.
4. Distinguish a **CORS preflight OPTIONS** from an ordinary HTTP OPTIONS request and from the actual GET/POST/PUT/DELETE request.
5. Understand why preflight must be processed **before Spring Security authentication** and must not require real cookies/tokens.
6. Configure `CorsConfiguration` and `UrlBasedCorsConfigurationSource` for **WebFlux**, integrated via `ServerHttpSecurity.cors(...)`.
7. Run a **Java 17+, Spring Boot 3.3.5, Spring Security 6.x** example, simulate requests with `curl`, and test with `WebTestClient`.
8. Troubleshoot common issues such as OPTIONS returning 401, rejected origins returning 403, CORS + CSRF, credentials, wildcards, and proxies.

**Scope:** CORS for Spring Security **reactive**; do not copy Servlet `CorsFilter` or `HttpSecurity` configurations verbatim into `SecurityWebFilterChain`. The examples use localhost and contain no production credentials.

## 2. What Is an Origin and When Does Cross-Origin Occur?

An **origin** is the **scheme + host + port** combination. URL paths and queries do not create a new origin.

For a primary frontend at `http://localhost:5173`:

| Request URL | Same origin as frontend? | Why? |
| --- | --- | --- |
| `http://localhost:5173/home` | Yes | Same scheme, host, and port |
| `http://localhost:5173/api/data` | Yes | A different path does not change the origin |
| `http://localhost:8080/api/data` | No | Different port |
| `https://localhost:5173/api/data` | No | Different scheme (HTTP/HTTPS) |
| `http://127.0.0.1:5173/api/data` | No | Different host even on the same machine |
| `https://api.example.test/data` | No | Different host and scheme |

CORS applies when **browser JavaScript** (`fetch`, `XMLHttpRequest`, etc.) makes a cross-origin request and wants to receive the response. Browsers enforce CORS under Fetch/Same-Origin Policy; a `curl` or backend-to-backend client **does not follow the same enforcement model**.

Do not equate **same-origin** with **same-site**. Two subdomains or ports can belong to the same site under cookie semantics while still having different origins and requiring CORS when JavaScript calls across them. Cookie `SameSite`, CSRF, authentication, and CORS are separate control layers.

### Browser Decision Flow

```text
JavaScript: fetch("http://localhost:8080/api/public")
                         |
                         v
          Compare against running page origin
                         |
              Same origin? -- Yes --> Send normal request
                         |
                        No
                         v
          Inspect method/headers/content type
                         |
               Satisfies CORS safelist?
                     /       \
                   Yes        No
                   |           |
                   v           v
              Send request  OPTIONS preflight
              directly         |
                   |       Server allows?
                   |        /           \
                   |       No           Yes
                   |       |             |
                   |       v             v
                   |    Browser      Send actual request
                   |    blocks       (GET/POST/...)
                   +-----------+---------+
                               |
                               v
                 Browser checks CORS response
                               |
                       Expose to JavaScript?
```

**Important:** For a simple cross-origin request, the browser **can send the actual request before discovering that the response is not readable by JavaScript**. Therefore, CORS does not replace authentication, authorization, CSRF, validation, or protection against state-changing side effects.

## 3. What Does "Simple Request" Mean?

The term "simple request" is widely used in CORS documentation. Technically, it refers to cross-origin requests that do not require a CORS preflight because their method, headers, and other attributes are **CORS-safelisted**.

To generally qualify as a simple request, the request must satisfy all relevant conditions:

- The method is **GET**, **HEAD**, or **POST**.
- Any request headers set explicitly by JavaScript belong to the **CORS-safelisted** set, such as `Accept`, `Accept-Language`, `Content-Language`, and `Content-Type` with qualifying values. `Range` can be safelisted for an allowed single-range format.
- When JavaScript sets `Content-Type`, the media type is one of the three permitted forms: `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`, along with header value constraints.
- None of the Fetch/XHR features that force preflight are present, such as certain XHR upload event listeners or streaming request bodies.
- Safelist byte/value length limits and value restrictions still apply; checking header names alone is not enough. Certain browser behaviors may vary.

**Not every POST requires a preflight**, though an **`application/json` POST usually does**, because `application/json` is not among the safelisted content types.

### Simple GET Example

JavaScript running from `http://localhost:5173`:

```javascript
const response = await fetch("http://localhost:8080/api/public");
console.log(response.status, await response.text());
```

If no other headers trigger preflight, the browser **sends the GET directly**, with `Origin: http://localhost:5173` for a CORS request.

A conceptual HTTP exchange:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Accept: */*
```

When the origin is allowed, the server may respond:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Content-Type: text/plain;charset=UTF-8

public-ok
```

The `Access-Control-Allow-Origin` header lets the browser expose the response to JavaScript at the specified origin. If that header is missing or does not match, **the server may still have processed the request and returned HTTP 200**, yet the browser prevents the script from reading the response.

### Example of a CORS-Simple POST

A POST with `Content-Type: text/plain` and no custom headers can be a simple request:

```javascript
await fetch("https://api.example.test/notes", {
  method: "POST",
  headers: { "Content-Type": "text/plain" },
  body: "hello"
});
```

This is a **CORS-principle example**, not a route in the Java demo in section 9. Just because a POST skips preflight **does not mean** the server accepts it: the endpoint must still enforce authentication/authorization, check CSRF when appropriate, validate the body, and control side effects.

### Commonly Misclassified Scenarios

| Browser request to another origin | Usually needs preflight? | Reason |
| --- | --- | --- |
| GET with `Accept: application/json` | No | GET and Accept satisfy the safelist |
| HEAD, no special extra headers | No | HEAD is a safelisted method |
| POST `Content-Type: text/plain` | No | POST and media type are safelisted |
| POST `application/x-www-form-urlencoded` | No | Form media type is safelisted |
| POST `multipart/form-data` | No under safelist conditions | Media type is safelisted, though other headers/conditions still apply |
| POST `application/json` | Yes | Content-Type is not safelisted |
| GET with `Authorization: Bearer ...` | Yes | Authorization is not safelisted |
| GET with `X-Client-Tag: web` | Yes | Custom header is not safelisted |
| PUT or DELETE | Yes | Method is not safelisted |
| GET with default browser cookie | Not just because of cookie | Credential mode is checked separately; a cookie alone does not trigger preflight |
| GET with safelisted header name but invalid value | Possibly yes | Fetch also enforces value/byte limits |

These examples assume standard cross-origin browser requests following Fetch; browser extensions, service workers, browser-specific limits, or non-browser environments may behave differently.

## 4. What Is a Preflight Request?

A **CORS preflight** is an HTTP **OPTIONS** request automatically generated by the browser **before the actual request** when the actual request uses a non-safelisted method or headers. Purpose: ask the server whether it accepts the **origin + intended method + intended headers**.

Example of JavaScript sending JSON:

```javascript
const response = await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ value: "hello" })
});
console.log(response.status);
```

The browser typically probes first:

```http
OPTIONS /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

Notes:
- Preflight always uses HTTP **OPTIONS**, while `Access-Control-Request-Method` holds the method **of the request to be sent next**: here, POST.
- `Access-Control-Request-Headers` lists the **header names** the browser plans to send, not their values. Here it is `content-type`, with **no** JSON body.
- `Origin` is the origin of the calling page; the browser usually sets it automatically.
- Preflight **does not send raw passwords/tokens in `Authorization`** and under the standard Fetch model does not carry the actual request's credentials. Do not require preflight to log in.
- Client-side JavaScript normally **does not need and should not manually craft OPTIONS preflights**. The browser decides on preflight based on the request.

The server agrees with a 2xx response and appropriate headers, for example:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET, HEAD, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Client-Tag
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Depending on the framework/config, the preflight response may be 200 or 204; **do not hardcode an expectation of 204**. The browser cares about 2xx and valid CORS headers.

If the browser accepts the preflight response, **only then does it send the actual POST**. The actual request can still receive **401**, **403**, **404**, **415**, **422**, or **500** for reasons independent of CORS. In the Spring Security demo below, a POST without a CSRF token still returns 403 even though preflight is permitted.

### Preflight for GET with a Custom Header

Even a GET can require a preflight:

```javascript
const response = await fetch("http://localhost:8080/api/public", {
  headers: { "X-Client-Tag": "frontend-demo" }
});
console.log(await response.text());
```

The browser sends an OPTIONS request containing:

```http
OPTIONS /api/public HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-client-tag
```

After a valid preflight, the browser sends the GET with `X-Client-Tag: frontend-demo`. The actual header value **is not sent in preflight**; preflight only asks for that header name to be permitted.

### Preflight with `Authorization`

A script preparing to send `Authorization` (Basic or Bearer) typically triggers a preflight because that header name **is not safelisted**:

```http
OPTIONS /api/private HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

This OPTIONS request **does not contain** the actual request's `Authorization: Basic ...` or `Authorization: Bearer ...`. If Security processes authentication **before CORS**, it can see an uncredentialed request and return `401 Unauthorized`, causing the browser to stop before sending the actual request.

**The right approach:** configure `CorsWebFilter`/CORS integration so preflight is evaluated **before authentication**, and then the actual GET request is authenticated and authorized.

## 5. How Does an Ordinary HTTP OPTIONS Differ from a CORS Preflight?

Not every HTTP OPTIONS request is a preflight.

Per Spring WebFlux's `CorsUtils.isPreFlightRequest` logic, a preflight is identified by:
- HTTP method **OPTIONS**;
- presence of the **Origin** header;
- presence of the **Access-Control-Request-Method** header.

The `Access-Control-Request-Headers` header is **optional**.

| Request | Is it a CORS preflight? | Interpretation |
| --- | --- | --- |
| `OPTIONS /api/public`, no Origin | No | Ordinary OPTIONS |
| `OPTIONS /api/public`, with Origin but no `Access-Control-Request-Method` | No | Has Origin but lacks preflight indicator |
| `OPTIONS /api/public` + Origin + `Access-Control-Request-Method: GET` | Yes | Browser asking whether GET may be sent |
| `OPTIONS /api/echo` + Origin + `Access-Control-Request-Method: POST` + `Access-Control-Request-Headers: content-type` | Yes | Browser asking about JSON POST |
| `OPTIONS /api/private` + Origin + `Access-Control-Request-Method: DELETE` | Yes in **form** | May be rejected by CORS because DELETE is not allowed |

An ordinary OPTIONS request can be routed to a handler, return 401/403/405, or return capability metadata depending on the system. **Do not write `@RequestMapping(method = OPTIONS)` just to fix CORS** when the real issue is a missing `CorsConfiguration`. With properly integrated WebFlux CORS, preflight can be handled and terminated **before reaching any controller**.

### OPTIONS Is Not the Actual Method

If a preflight asks:

```http
Access-Control-Request-Method: DELETE
```

the browser is asking **whether DELETE may be sent afterward**, not trying to invoke a business endpoint that performs DELETE via OPTIONS itself. A valid preflight does not delete data and carries no business JSON request body.

**Security policy:** You can allow handling **uncredentialed** OPTIONS preflight while still requiring authentication/authorization for the actual DELETE. Do not infer "OPTIONS passed" = "DELETE needs no permissions".

## 6. CORS Headers You Need to Know How to Read

### Browser Request Headers

| Header | Where used | Meaning |
| --- | --- | --- |
| `Origin` | Simple, preflight, and actual CORS | Origin of the calling JavaScript page |
| `Access-Control-Request-Method` | OPTIONS preflight | Method of the upcoming actual request |
| `Access-Control-Request-Headers` | OPTIONS preflight when needed | List of header names for the actual request |
| `Authorization` | Actual request if client uses auth header | Authentication material; not a default preflight header |
| `Cookie` | Actual request when browser credential mode and cookie policy allow | Session/credential, does not necessarily trigger preflight |

The request headers `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers` are managed by the browser. JavaScript should not attempt to set these forbidden headers manually.

### Server Response Headers

| Header | Meaning | Notes |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | Origin allowed by the browser to read the response | Must match the origin, or `*` only in permitted cases |
| `Access-Control-Allow-Methods` | Methods permitted for preflight | Typically lists GET/POST/PUT/DELETE... per policy |
| `Access-Control-Allow-Headers` | Request headers permitted for preflight | E.g., `Content-Type`, `Authorization`, `X-Client-Tag` |
| `Access-Control-Allow-Credentials` | Allows JavaScript to receive a credentialed response when all other conditions pass | Enable only when truly needed; never combine with wildcard origin `*` |
| `Access-Control-Max-Age` | Seconds the browser may cache the preflight result | Browsers may impose their own cap; preflight cache differs from normal HTTP caching |
| `Access-Control-Expose-Headers` | Extra response headers JS may read | Does not turn a header into proof of authorization |
| `Vary` | Tells caches that the response depends on Origin and related request headers | Important for CDNs/reverse proxies and multiple origins |

**`Access-Control-Allow-Origin` is not authentication.** The server must still enforce permissions and filter data for the principal/role, even when the origin is valid. CORS remains a browser cross-origin JavaScript boundary, not a server ACL.

## 7. CORS, Credentials, CSRF, and Spring Security Are Four Separate Concerns

### 7.1. Preflight Has No Actual-Request Credentials

Spring Security officially notes that **CORS must be processed before Spring Security**, because preflights normally do not carry cookies/sessions or actual-request credentials. If an authentication filter intercepts OPTIONS first and demands login, the browser can encounter a 401 or redirect preflight failure.

Proper coordination:

```text
Cross-origin OPTIONS preflight
          |
          v
    CORS validation
      /         \
    reject      allow
      |           |
     403        2xx + CORS headers
                  |
          Browser decides to send
              actual request
                  |
                  v
        CORS response processing
                  |
                  v
           Authentication
                  |
                  v
           Authorization
                  |
                  v
              CSRF check
         (when method/client requires)
                  |
                  v
              Controller
```

This diagram illustrates separation of responsibilities, not the exact internal order of every WebFilter. `ServerHttpSecurity.cors(...)` places `CorsWebFilter` at the proper position in Spring Security reactive.

### 7.2. Successful Preflight != Successful Authentication

For example, an allowed origin sends OPTIONS `/api/private` requesting method GET and header `Authorization`. The server can permit OPTIONS before knowing who the user is. The browser then sends the actual GET; without valid `Authorization`, it receives **401 Unauthorized**.

Likewise, allowing an origin to send POST does not prove the principal has the right role or a valid CSRF token; the actual request can still get 403.

### 7.3. CORS Does Not Replace CSRF

CORS decides whether JavaScript from another origin may **read the response**. CSRF defends against **state-changing** operations caused by the browser automatically attaching credentials (cookies/Basic in certain cases) without user intent.

A cross-origin **simple POST** can be sent by the browser **without a preflight**; therefore, preflight must never be treated as CSRF protection. With cookie/session-based logins, keep appropriate CSRF defenses regardless of how tightly you lock down CORS.

The demo in section 9 **keeps default CSRF enabled**. A JSON POST passes preflight, yet the actual POST without a CSRF token returns **403**. This is an **intentional and correct** result so learners do not confuse CORS with CSRF.

### 7.4. `allowCredentials` and Wildcards

If the frontend must send cross-origin cookies/sessions (`fetch(..., { credentials: "include" })`), the response must include `Access-Control-Allow-Credentials: true` and a **specific `Access-Control-Allow-Origin`, never `*`**, alongside appropriate `SameSite`/`Secure` cookie attributes. This **does not exempt CSRF**, nor does it force the browser to send cookies if cookie policies forbid it.

The lesson example uses `setAllowCredentials(false)` to make clear that **a public-origin CORS demo does not grant cross-origin cookie transmission**. Switching to a credentialed browser session app requires redesigning the origin allowlist, cookie attributes, CSRF, and authentication—not flipping a single boolean.

For script-set `Authorization`, the header name is **not safelisted**, so preflight occurs; whether the browser actually sends credentials also depends on the Fetch credentials mode and client policy. Never hardcode raw passwords/tokens in public JavaScript.

### 7.5. CORS Does Not Restrict `curl` or Service-to-Service Calls

Non-browser callers can send HTTP requests directly with no `Origin` or any fabricated `Origin`. CORS is **not** an authentication/authorization mechanism for backends. Protect APIs with OAuth2/JWT, Basic over HTTPS, mTLS, sessions, or appropriate authentication combined with authorization.

## 8. Designing CORS Configuration for Spring WebFlux

In Spring Security reactive, use:

- `org.springframework.web.cors.CorsConfiguration` (common framework configuration).
- `org.springframework.web.cors.reactive.CorsConfigurationSource` or `UrlBasedCorsConfigurationSource` (**reactive** package).
- `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))` on `SecurityWebFilterChain`.

Do not confuse Servlet's `org.springframework.web.cors.UrlBasedCorsConfigurationSource` with `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. The two classes belong to different web stacks.

### Path and Origin Scope

Suppose the development frontend runs at `http://localhost:5173` and the API runs at `http://localhost:8080`:

- Allowlist the **exact** origin `http://localhost:5173`, rather than opening all origins `*`.
- Register CORS for `/api/**`, avoiding accidentally opening every application endpoint unnecessarily.
- Methods: `GET`, `HEAD`, `POST`, `OPTIONS`.
- Allowed headers: `Content-Type`, `Authorization`, `X-Client-Tag`.
- Credentials: **false** in the demo; requests do not use cross-origin cookies.
- Preflight cache: `maxAge=600` seconds, subject to browser-specific caps.
- Exposed header: `X-Demo-Trace` to illustrate the difference between sent headers and headers JS is allowed to read.

An important design detail: **`allowedMethods` can include OPTIONS**, yet during preflight the browser asks for the actual method such as POST; simply adding OPTIONS to the allowlist does not allow POST, PUT, or DELETE. The policy must include the requested actual method.

### Avoid Unintentionally Duplicating Two CORS Mechanisms

CORS can be configured at the WebFlux handler level (`@CrossOrigin`, `WebFluxConfigurer.addCorsMappings`), in `CorsWebFilter`, or in Spring Security. For a single service, choose **one clear strategy**, keep it consistent within the security chain, and test it. If you combine `@CrossOrigin("*")` with a strict global config, understand how they merge—never assume "whichever config is stricter automatically wins".

The example below uses **a single `UrlBasedCorsConfigurationSource` passed directly to `ServerHttpSecurity.cors`**. No extra standalone `CorsWebFilter` bean is created, avoiding double-processing and header duplication in the demo.

## 9. Runnable Project: Spring Boot 3.3.5 + WebFlux + CORS

The code targets **Java 17+**, **Gradle 8.x compatible**, and **Spring Boot 3.3.5**. Spring Security 6.x is managed by Spring Boot without pinning a separate Spring Security version.

Structure:

```text
reactive-cors-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/cors/
    │   ├── CorsDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/cors/
        └── CorsSecurityTests.java
```

### 9.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-cors-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Why use only the WebFlux starter?** Adding `spring-boot-starter-web` alongside it typically causes Spring Boot to choose Servlet/MVC. That uses different CORS/Security classes than this lesson and interferes with reactive testing.

### 9.2. Application Entry Point

`src/main/java/dev/example/cors/CorsDemoApplication.java`:

```java
package dev.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

### 9.3. CORS and Spring Security Reactive Configuration

`src/main/java/dev/example/cors/SecurityConfig.java`:

```java
package dev.example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(
                List.of("GET", "HEAD", "POST", "OPTIONS"));
        config.setAllowedHeaders(
                List.of("Content-Type", "Authorization", "X-Client-Tag"));
        config.setExposedHeaders(List.of("X-Demo-Trace"));
        config.setAllowCredentials(false);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
                .cors(cors -> cors.configurationSource(corsSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/private")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST, "/api/echo")
                            .permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Section-by-section explanation:**

1. The `UrlBasedCorsConfigurationSource` bean is the **reactive** variant, resolving CORS policy by URL path. We apply it only to `/api/**`.
2. `setAllowedOrigins(...)` accepts **`http://localhost:5173`**. `https://localhost:5173`, `http://127.0.0.1:5173`, or another port will not be allowed automatically.
3. `setAllowedMethods(...)` permits preflight checks for GET, HEAD, POST, OPTIONS. If the frontend starts sending PUT, evaluate business requirements and add PUT to both the policy and the route.
4. `setAllowedHeaders(...)` lets the browser request `Authorization`, `Content-Type`, or `X-Client-Tag` in `Access-Control-Request-Headers`. This is neither an authorization mechanism nor automatic token acceptance.
5. `setAllowCredentials(false)` does not advertise support for cross-origin cookies/sessions. Switching to cookie-based browser logins requires a different, controlled configuration.
6. `setMaxAge(600L)` sets the maximum preflight cache duration per server policy; browsers may enforce their own cap.
7. `http.cors(cors -> cors.configurationSource(corsSource))` integrates CORS handling into the proper Spring Security order, **letting OPTIONS preflight run before authentication**.
8. HTTP rules make `GET /api/public` public and require login for `GET /api/private`. `POST /api/echo` is public at the authorization layer solely to observe CSRF; it remains subject to **default CSRF protection**.
9. `anyExchange().denyAll()` fails closed for undesigned methods/paths. Adding `pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` is **not** enough if CORS headers are missing.
10. `httpBasic` lets us test the private GET with a sample account. `formLogin` is disabled so 401 is easy to observe; `csrf` is not disabled.
11. The localhost account/password is strictly for **demo** use. For real network traffic, HTTP Basic must travel over valid HTTPS/TLS.

**Why is preflight to `/api/echo` accepted even when the actual POST lacks CSRF?** CORS checks origin/method/headers **at the browser protocol step**, whereas CSRF protects the **actual POST** request. These are two distinct layers and a core takeaway of this lesson.

### 9.4. WebFlux Controller

`src/main/java/dev/example/cors/DemoController.java`:

```java
package dev.example.cors;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record EchoInput(String value) {
    }

    @GetMapping("/api/public")
    public Mono<String> publicPage(ServerHttpResponse response) {
        response.getHeaders().set("X-Demo-Trace", "public-demo");
        return Mono.just("public-ok");
    }

    @GetMapping("/api/private")
    public Mono<String> privatePage(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }

    @PostMapping(
            value = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<EchoInput> input) {
        return input.map(value -> Map.of("echo", value.value()));
    }
}
```

`/api/public` and `/api/private` let us observe simple GET, preflight GET with a custom header, and authentication. `/api/echo` represents a JSON POST showing that **OPTIONS preflight succeeds**, while an actual POST without CSRF is rejected. The project contains no `@RequestMapping(method = OPTIONS)` handler: preflight is handled by the CORS layer.

The controller returns `Mono` and never calls `block()` or `subscribe()`. Production JSON inputs must include validation and proper `null` handling; the demo merely echoes one field.

## 10. Hands-On Verification with curl

From the `reactive-cors-demo` directory:

```bash
gradle bootRun
```

If you have the Gradle Wrapper, use `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). By default the application runs on `http://localhost:8080`. In PowerShell, if `curl` is an alias, use `curl.exe` to invoke the curl binary.

**Warning:** `curl` does not enforce the Same-Origin Policy and **does not automatically send preflight requests** like a browser. To simulate preflight, you must send `OPTIONS` and the relevant headers **manually**.

### 10.1. Simple Cross-Origin GET

```bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/public
```

Expected:
- HTTP **200**, body `public-ok`.
- `Access-Control-Allow-Origin: http://localhost:5173`.
- `Access-Control-Expose-Headers` containing `X-Demo-Trace`, plus response header `X-Demo-Trace: public-demo`.
- No `OPTIONS` request is automatically emitted by **curl** simply because you supplied `Origin`.

Browser JavaScript from `http://localhost:5173` can read the response when CORS headers are valid. Requests from another origin behave differently.

### 10.2. OPTIONS Preflight for GET with a Custom Header

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-client-tag' \
  http://localhost:8080/api/public
```

Expected:
- Preflight returns **2xx** (not fixed to 200 or 204).
- `Access-Control-Allow-Origin` matches the origin.
- `Access-Control-Allow-Methods` indicates GET is accepted.
- `Access-Control-Allow-Headers` indicates `X-Client-Tag` is accepted.
- Body may be empty; **the GET controller is not invoked** because this is an OPTIONS preflight.

Afterward, the browser sends the actual GET with `X-Client-Tag` and receives a response per security rules.

### 10.3. OPTIONS Preflight for JSON POST

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type' \
  http://localhost:8080/api/echo
```

Expected: **2xx** with CORS allow headers for POST and `Content-Type`.

However, if you send the actual POST **without a CSRF token**:

```bash
curl -i -X POST \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  --data '{"value":"hello"}' \
  http://localhost:8080/api/echo
```

Expected: **403 Forbidden** from **CSRF protection**, not because JSON POST was rejected by CORS. The CORS policy allowed the origin/method/header; Spring Security CSRF is a separate layer. Do not disable CSRF just to make this POST return 200 if browsers will use the app and send sessions/credentials automatically.

### 10.4. OPTIONS Preflight with Authorization for a Protected Endpoint

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,x-client-tag' \
  http://localhost:8080/api/private
```

Expected: **2xx**, even though OPTIONS does not send an actual `Authorization` header.

Actual GET without credentials:

```bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/private
```

Expected: **401 Unauthorized** (invalid/missing authentication).

Actual GET with HTTP Basic:

```bash
curl -i --user reader \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/private
```

Curl prompts interactively for the password; enter the **localhost demo** password `reader-pass`. Expected **200**, body `user=reader`. With real credentials, always use HTTPS and never put passwords directly in command lines or shell history.

### 10.5. Disallowed Origin

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://untrusted.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  http://localhost:8080/api/public
```

Expected: **4xx**, typically `403 Invalid CORS request` from Spring WebFlux's default CORS processor; no valid CORS response is returned for that origin. When a browser receives a failed preflight, it **does not send the actual request** for the CORS flow under test.

### 10.6. Disallowed Method or Header

Try requesting DELETE when the configuration only allows GET/HEAD/POST/OPTIONS:

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE' \
  http://localhost:8080/api/public
```

Expected: **4xx** (CORS does not permit DELETE).

Similarly, a preflight requesting `X-Secret-Debug`, which is not in `setAllowedHeaders`, will be rejected. Do not fix this with an unchecked `allowedHeaders("*")` when you can list only the headers the application needs.

### 10.7. Ordinary OPTIONS, Not a Preflight

```bash
curl -i -X OPTIONS http://localhost:8080/api/public
```

This is **not** a CORS preflight because it lacks `Origin` and `Access-Control-Request-Method`. It may receive 401/403/405 depending on security rules and routing; the demo uses `anyExchange().denyAll()`, so it does not treat this request as an allowed preflight. **Do not conclude CORS is broken just because an OPTIONS lacking preflight headers is rejected.**

## 11. Testing Directly with a Browser and DevTools

To observe firsthand how the browser decides whether to preflight, run a development frontend at `http://localhost:5173`, open DevTools **Network**, and enable filters to show OPTIONS/Fetch requests. For example, from that page's JavaScript console:

### Case A — Simple GET, No OPTIONS

```javascript
const r1 = await fetch("http://localhost:8080/api/public");
console.log(r1.status, await r1.text()); // Expected: 200 public-ok
```

If nothing else requires preflight, Network shows only GET. JS can read the response thanks to the matching `Access-Control-Allow-Origin`.

### Case B — GET with Custom Header, Triggers OPTIONS

```javascript
const r2 = await fetch("http://localhost:8080/api/public", {
  headers: { "X-Client-Tag": "web-v1" }
});
console.log(r2.status, await r2.text()); // Expected: 200 public-ok
```

Network will show:
1. `OPTIONS /api/public` asking for GET + x-client-tag.
2. The actual `GET /api/public` after preflight is accepted.

If the browser has already cached a valid preflight, **you may not see a repeated OPTIONS** on the second run. In DevTools, use a fresh session or vary the request appropriately to observe it again.

### Case C — JSON POST with OPTIONS, Actual 403 Due to CSRF

```javascript
const r3 = await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ value: "hello" })
});
console.log(r3.status); // Expected: 403 without CSRF
```

The browser sends OPTIONS because of the JSON `Content-Type`. Once preflight is allowed, the actual POST proceeds and is rejected by the CSRF filter. **This is not a CORS error.** If the frontend needs state-changing browser APIs, design CSRF tokens, authentication, and cookie policies alongside CORS.

### Case D — Origin Mismatch

If called from `http://127.0.0.1:5173` or `https://localhost:5173`, the origin does not match the `http://localhost:5173` allowlist, so the browser reports a CORS error. CORS compares scheme, host, and port **exactly**. Do not "open everything" just because a dev server changed ports; add specific development origins and manage them per environment.

### When Network Shows No OPTIONS

Possible reasons:
- The actual request satisfies the CORS safelist (simple).
- The preflight result is still in the browser cache.
- The request originates from the same origin, not cross-origin.
- The browser aborted before sending due to a JS error, mixed content, or an extension.
- The tool you used **is not a browser**, such as `curl`, Postman, or a backend script.

Do not see an absence of OPTIONS once and assume the server lacks CORS; verify the actual request and Fetch conditions.

## 12. Integration Testing with WebTestClient

This is a critical QA step because CORS bugs often live in **security filter ordering**, not just controllers. Tests send headers simulating a browser, though they **do not enforce real browser CORS behavior**. You should still verify with DevTools/E2E in a real browser.

File `src/test/java/dev/example/cors/CorsSecurityTests.java`:

```java
package dev.example.cors;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsSecurityTests {

    private static final String ORIGIN = "http://localhost:5173";

    @Autowired
    WebTestClient client;

    @Test
    void simpleGetFromAllowedOriginSucceedsWithCorsHeader() {
        client.get().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void requestWithoutOriginIsNotACorsRequest() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void allowedPreflightForGetCustomHeaderDoesNotNeedLogin() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-client-tag")
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectHeader().value(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                        value -> assertTrue(
                                value.toLowerCase().contains("x-client-tag")));
    }

    @Test
    void allowedPreflightForJsonPostSucceedsWithoutCsrf() {
        client.options().uri("/api/echo")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type")
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectHeader().value(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                        value -> assertTrue(value.contains("POST")));
    }

    @Test
    void actualPostWithoutCsrfIsRejectedDespiteCors() {
        client.post().uri("/api/echo")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("value", "hello"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN);
    }

    @Test
    void preflightForProtectedGetIsAcceptedWithoutCredentials() {
        client.options().uri("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization,x-client-tag")
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN);
    }

    @Test
    void actualProtectedGetWithoutAuthenticationIs401() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void actualProtectedGetWithAuthenticationIs200() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void preflightFromUnknownOriginIsRejected() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN,
                        "http://untrusted.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void preflightWithDisallowedMethodIsRejected() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void preflightWithDisallowedHeaderIsRejected() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-secret-debug")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void ordinaryOptionsWithoutPreflightHeadersIsNotGrantedCorsBypass() {
        client.options().uri("/api/public")
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
```

Run:

```bash
gradle test
```

**Expected result:** 12 tests passing with the complete configuration above and compatible dependencies. This is an **expectation derived from the APIs and code logic**, **not a claim that Gradle was executed in your workspace**. When running on a real system, inspect the test report and logs to confirm.

### What the Tests Mean

1. Simple GET from allowed origin returns 200 and proper ACAO.
2. Same-origin/no-Origin GET needs no CORS header.
3. OPTIONS GET with custom header is accepted without login.
4. OPTIONS JSON POST returns 2xx, confirming POST is permitted.
5. Actual JSON POST without CSRF returns 403 even with valid CORS.
6. OPTIONS for private endpoint requires no credentials.
7. Actual private GET without login still returns 401.
8. Private GET with valid Basic auth returns 200.
9. Origin outside allowlist gets 403 on preflight.
10. Disallowed DELETE method gets 403.
11. Disallowed `x-secret-debug` header gets 403.
12. OPTIONS lacking preflight indicators **receives no special bypass** just for being OPTIONS.

**Why do preflight tests use `is2xxSuccessful()`?** A successful preflight HTTP status can be 200 or 204 depending on framework/configuration. CORS semantics depend on a successful status and allow headers, not one fixed status code across all implementations.

**Why does test 12 use `is4xxClientError()`?** An ordinary OPTIONS can return 401, 403, or 405 depending on authentication/authorization/routing. What matters is not confusing it with a valid CORS preflight, not forcing one specific 4xx code.

### Extending Tests with Mock CSRF

If you want to prove the POST endpoint actually runs with a valid CSRF token, you can use Spring Security Test with `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` and `mutateWith(csrf())`. This is an **extended testing pattern**, not included in `CorsSecurityTests` (which uses `RANDOM_PORT`), because mock CSRF is normally applied to a client bound to the Spring application context:

```java
// JUnit fragment with @Autowired ApplicationContext context.
// Requires testImplementation 'org.springframework.security:spring-security-test'.
WebTestClient secureClient = WebTestClient
        .bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();

secureClient.mutateWith(SecurityMockServerConfigurers.csrf())
        .post().uri("/api/echo")
        .header("Origin", "http://localhost:5173")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("value", "hello"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.echo").isEqualTo("hello");
```

This is a **fragment, not a standalone Java file**; it needs imports for `ApplicationContext`, `SecurityMockServerConfigurers`, `WebTestClient`, `Map`, and `MediaType`, plus the test dependency noted in the comment. It verifies that a **POST with a CSRF token** is processed, not how a browser obtains and attaches a CSRF token. For real browser apps, design an appropriate CSRF token repository and client flow.

## 13. Diagnosing Errors When the Frontend Reports "CORS error"

### 13.1. Distinguishing Browser Blocking from Server Errors

When DevTools reports:

```text
Access to fetch at ... from origin ... has been blocked by CORS policy
```

check the following:
1. Did the browser send `OPTIONS`?
2. What was the `OPTIONS` status—was it redirected to login or 401?
3. What were the request headers `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`?
4. Were the response headers `Access-Control-Allow-Origin`, `Allow-Methods`, and `Allow-Headers` correct?
5. Did the browser send the actual request after `OPTIONS`?
6. Did the actual request return 401/403/500 due to authentication/CSRF/authorization?
7. Did a reverse proxy/gateway strip or modify CORS headers?

A CORS error shown in the browser **does not prove a Spring Controller ran**; preflight may have been blocked before reaching the controller. Conversely, a 401/403 response with valid ACAO allows JavaScript to see the status/body if security/browser policy permits, and that is an **authentication/authorization error**, not a CORS error.

### 13.2. "Preflight response is not successful" / OPTIONS 401

**Common cause:** Security intercepts `OPTIONS` before CORS and requires login, or a gateway redirects to login/HTTPS. Preflight carries no real cookie/token and gets 401/302.

**Fix:** Integrate `CorsConfigurationSource` into `ServerHttpSecurity.cors(...)` or order a `CorsWebFilter` properly; inspect gateway and security chains. Do not just add `OPTIONS permitAll` while neglecting allow headers.

### 13.3. "No Access-Control-Allow-Origin" Even Though the API Returned 200

Possible causes:
- The origin is not in `allowedOrigins`.
- The CORS source is registered on the wrong path, e.g. `/api/**` while the request hits `/auth/**`.
- Configured on only one security chain while the request hits another chain.
- CORS processing is disabled via `cors(cors -> cors.disable())`.
- A proxy/cache stripped the header or the response came from a gateway error page.

Use DevTools/curl with the exact `Origin` to inspect the response, not just the status code.

### 13.4. "Request header field authorization is not allowed"

Preflight `Access-Control-Request-Headers` contains `authorization`, yet `allowedHeaders` in the policy does not permit it. Add the required **header name** to the allowlist, and ensure the actual request still passes authentication. **Never return tokens** inside `Access-Control-Allow-Headers`: it is a list of header names, not secret values.

### 13.5. "Method PUT is not allowed"

The origin is valid, but `Access-Control-Request-Method: PUT` is not in `allowedMethods`. Evaluate whether the business endpoint supports PUT, then update both the CORS policy and HTTP routing/authorization. Avoid using `allowedMethods("*")` when you can enumerate the real methods.

### 13.6. Preflight 2xx Yet Actual POST Returns 403

This is the intentional demo scenario: CORS accepted the origin/method/headers, but the actual POST lacked a **CSRF token**. It can also stem from missing permissions, an expired session, or invalid authentication.

**Fix:** inspect security status and the CSRF flow; do not disable CSRF by default for browser-session apps.

### 13.7. Cookies Missing on Cross-Origin Calls

Review:
- `fetch(..., { credentials: "include" })` and server `Access-Control-Allow-Credentials: true`.
- Specific origin, **not** `*`, when credentialed.
- Cookie `SameSite=None; Secure` when cross-site usage requires it, real HTTPS, and browser third-party cookie policies.
- Cookie `Domain`/`Path`/`Secure`/`HttpOnly` attributes and proxy behavior.
- CSRF token if the request changes state.

This demo **intentionally sets `allowCredentials(false)`**, so it is not configured for a cross-origin frontend using session cookies. Do not flip it to `true` just because the frontend shows an error without evaluating your threat model.

### 13.8. Preflight Gets Redirected

Some browsers do not handle redirects on preflight as expected. If a proxy upgrades HTTP→HTTPS or rewrites paths, configure the frontend to call the **final HTTPS URL directly** to avoid preflight redirects when possible. Ensure the gateway emits proper CORS headers on all routes/errors. When `Authorization` triggers preflight, the client cannot easily avoid preflight simply by tweaking request syntax.

### 13.9. `null` Origin and file://

Sources like sandboxed iframes, `file://`, or certain opaque-origin documents can send `Origin: null`. Do not permit `null` casually, as it can admit untrusted sources. During development, serve the frontend from a local HTTP server with an explicit origin and allowlist it accurately.

### 13.10. Browser Preflight Caching

`Access-Control-Max-Age` drives the browser's own preflight cache, subject to per-browser caps. You may see `OPTIONS` on the first request and not on subsequent ones. When debugging config changes, test in a fresh session or vary the request rather than assuming the server ignored CORS. Caches/CDNs should respect `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` to avoid serving responses for the wrong origin/headers.

## 14. Security Principles When Configuring CORS

| Configuration or habit | Risk / misconception | Recommended practice |
| --- | --- | --- |
| `allowedOrigins("*")` for cookie APIs | Credentialed browser requests cannot use wildcard origin per spec; overly broad elsewhere | List only required origins |
| `allowedHeaders("*")` everywhere | Unnecessarily widens JS request header surface | Allow only approved headers |
| `allowedMethods("*")` as a quick fix | Harder to govern accepted HTTP methods | List GET/POST/... per API contract |
| `OPTIONS /** permitAll` without CORS config | Preflight still lacks allow headers | Integrate CORS filter/source |
| Requiring login/CSRF on preflight | Browser refuses to send actual request | Process preflight before security |
| Treating preflight 2xx as logged-in user | OPTIONS carries no real credentials | Authenticate the actual request |
| Dropping CSRF because CORS is enabled | Simple POST can still be sent and cause side effects | Evaluate CSRF independently |
| Trusting `Origin` as proof of valid user | Non-browser callers easily spoof `Origin` | Enforce authn/authz |
| Returning `Access-Control-Allow-Origin` improperly for caches | CDN may serve wrong-origin response | Configure `Vary` and caching properly |
| Combining `@CrossOrigin("*")` with another global policy | Hard to predict composition, easy to over-expose | Pick one controlled strategy |
| Uncoordinated CORS in both gateway and app | Duplicate/missing headers, blocked OPTIONS | Unify ownership and test E2E |
| Storing Basic passwords in JS | Exposes secrets in bundle/browser | Never hardcode credentials; use proper auth flows |
| Using `curl` and assuming browser CORS works | Curl does not enforce CORS | Test via DevTools/browser E2E |
| Concluding CORS error from 403 alone | 403 could be CSRF or authorization | Check whether OPTIONS or actual, inspect headers |
| Unconditionally allowing `Origin: null` | Opaque origins may be untrusted | Allow only when threat model permits |

## 15. Quick Ordered Debugging Checklist

1. **Actual origin:** copy the exact `Origin` from browser Network; verify scheme/host/port.
2. **Is there a preflight?** Look for `OPTIONS` and its request headers.
3. **Correct route:** what path does `OPTIONS` hit? Does `CorsConfigurationSource` cover that path?
4. **Uncredentialed preflight:** avoid requiring cookies/tokens on `OPTIONS`.
5. **Methods:** is `Access-Control-Request-Method` permitted?
6. **Headers:** are all names in `Access-Control-Request-Headers` permitted?
7. **Status:** preflight is 2xx; if 3xx/4xx/5xx, check proxy/filters first.
8. **CORS response headers:** are ACAO/Allow-Methods/Allow-Headers/Max-Age and Vary accurate?
9. **Actual request:** was it sent after `OPTIONS`? If so, 401/403 may belong to auth/CSRF.
10. **Credentialed mode:** if using cookies, check `Allow-Credentials`, specific origin, SameSite/Secure.
11. **Caching:** is browser preflight cache or CDN hiding config changes?
12. **Two-sided verification:** `curl` to simulate protocol, DevTools to confirm browser enforcement, and Spring Security tests to confirm ordering.

## 16. Self-Check Questions

**1. What components make up an Origin?**  
**Answer:** Scheme, host, and port. Paths and queries do not create a different origin.

**2. Do `http://localhost:5173` and `http://localhost:8080` share the same origin?**  
**Answer:** No, they have different ports.

**3. Does a GET without custom headers require a preflight?**  
**Answer:** Normally no, provided all other CORS safelist conditions are satisfied.

**4. Does an `application/json` POST require a preflight?**  
**Answer:** Normally yes, because `Content-Type` is not one of the three safelisted media types.

**5. Does a GET with `Authorization` require a preflight?**  
**Answer:** Yes in browser CORS, because `Authorization` is not safelisted.

**6. Which HTTP method does preflight always use?**  
**Answer:** OPTIONS.

**7. Does `Access-Control-Request-Method: DELETE` mean OPTIONS is deleting data?**  
**Answer:** No; it asks the server whether an actual DELETE may be sent afterward.

**8. What three headers identify a preflight request?**  
**Answer:** HTTP OPTIONS plus `Origin` and `Access-Control-Request-Method`; `Access-Control-Request-Headers` is optional.

**9. Does the browser send the raw Basic/JWT token in preflight?**  
**Answer:** Under the standard preflight flow, it does not send the actual request's `Authorization` value; it only lists the header name `authorization`.

**10. Does a 2xx preflight guarantee the actual POST returns 200?**  
**Answer:** No. The actual POST still goes through authentication, authorization, CSRF, validation, and business logic.

**11. Why must CORS run before Spring Security authentication?**  
**Answer:** Preflights lack the actual request's credentials; if Security demands login first, OPTIONS can fail with 401 or a redirect.

**12. Is `OPTIONS /api/public` without `Origin` and `Access-Control-Request-Method` a preflight?**  
**Answer:** No, that is an ordinary OPTIONS request.

**13. Is `Access-Control-Allow-Origin: *` valid with a credentialed `allowCredentials=true` response?**  
**Answer:** No. Credentialed browser requests require a specific allowed origin and valid `Allow-Credentials`.

**14. Can CORS be used to stop `curl` from calling an API?**  
**Answer:** No. CORS is browser enforcement; server-to-server clients and curl are not restricted by CORS.

**15. If a JSON POST preflight succeeds yet returns 403, what should you check?**  
**Answer:** Confirm the 403 came from the actual POST, then check CSRF token, authentication, and authorization before altering CORS.

**16. Why does the browser sometimes skip sending `OPTIONS` again?**  
**Answer:** The preflight response may be cached for a period; the request may also have changed to become simple or same-origin.

**17. Do you need a dedicated `@RequestMapping(OPTIONS)` controller for CORS?**  
**Answer:** No, if the CORS layer handles preflight properly; ordinary OPTIONS controllers serve other purposes.

**18. How does `Vary` help in CORS?**  
**Answer:** It instructs caches to distinguish responses by `Origin` and related request method/headers so CORS headers are not served out of context.

### Practice Exercises

1. Run the demo, use `curl -H Origin` and DevTools to compare whether a simple GET triggers OPTIONS. Describe the difference between the CLI tool and the browser.
2. From the `http://localhost:5173` frontend, send a GET with `X-Client-Tag`, locate OPTIONS in Network, and inspect `Access-Control-Request-Headers`.
3. Change `X-Client-Tag` to `X-Unknown` without updating the CORS policy; observe the blocked preflight. Intentionally update `allowedHeaders` to understand the rule.
4. Send an OPTIONS requesting DELETE before DELETE is in `allowedMethods`; explain why this is a CORS rejection rather than a DELETE controller error.
5. Send an OPTIONS to `/api/private` with `Access-Control-Request-Headers: authorization` **without** Basic credentials; verify 2xx, then send the actual GET unauthenticated and observe 401.
6. Try a JSON POST without CSRF: preflight 2xx yet actual 403. Summarize the difference between CORS and CSRF.
7. Switch the frontend origin to `http://127.0.0.1:5173` or port 3000, verify the exact-origin policy, and update the allowlist for development if needed.
8. On a session-authenticated browser app, design `allowCredentials`, cookie `SameSite`/`Secure`, and CSRF properly; explain why turning on a wildcard does not work.
9. Add an `Access-Control-Expose-Headers` test for `X-Demo-Trace`; note that exposing a header does not make sensitive data safe.
10. Diagram the flow of a preflight and actual request through a reverse proxy/gateway; pinpoint where CORS can be blocked or headers rewritten.
11. Lower `setMaxAge(600L)` to a short duration in a test environment and observe preflight caching (a fresh browser/profile may be needed).
12. Add an `ADMIN`-protected GET endpoint and verify that a valid origin + successful preflight still returns 403 for a user lacking the role.

## 17. Official References

- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS must be processed before Spring Security, with `UrlBasedCorsConfigurationSource` and `CorsWebFilter` examples.
- [Spring Security 6.x API — ServerHttpSecurity.CorsSpec](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html): `configurationSource` and how Spring Security integrates CORS.
- [Spring Framework 6.1 — WebFlux CORS API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/cors/reactive/package-summary.html): reactive `CorsWebFilter`, `CorsConfigurationSource`, `UrlBasedCorsConfigurationSource`.
- [Spring Framework — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `@CrossOrigin`, global CORS configuration, preflight processing.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): simple requests, preflighted requests, safelist, and credentialed requests.
- [MDN — Preflight request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request): OPTIONS and `Access-Control-Request-Method`.
- [MDN — HTTP OPTIONS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/OPTIONS): distinguishing the purpose of OPTIONS vs. CORS preflight.
- [MDN — CORS errors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors): how to interpret browser errors.
- [Fetch Standard](https://fetch.spec.whatwg.org/): CORS-safelisted request conditions, preflight, and credential modes.
- [Spring Security — CSRF testing in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): testing CSRF independently of CORS with `WebTestClient`.

**Remember:** A **simple cross-origin request** goes straight to the server, yet the browser still checks CORS on the response. **Non-safelisted methods, headers, or content types** make the browser send an **OPTIONS preflight** first; OPTIONS asks about the **actual request's** method/headers and does not carry real login credentials. In **Spring Security reactive**, CORS must be processed **before authentication**; a passing preflight **does not exempt** the actual request from authentication, authorization, or CSRF.