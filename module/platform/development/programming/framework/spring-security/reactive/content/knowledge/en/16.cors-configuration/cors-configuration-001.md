# Same-Origin Policy, Origin, and the Purpose of CORS in Spring Security WebFlux

## Lesson Goals and Scope

This lesson belongs to the **CORS Configuration** group in the **Spring Security - reactive** module. Before changing `CorsWebFilter` or `ServerHttpSecurity.cors(...)`, you need to understand that the **Same-Origin Policy (SOP)** is a rule enforced by the *browser*; an **origin** is defined by the scheme–host–port tuple; and **Cross-Origin Resource Sharing (CORS)** is the mechanism by which the server informs the browser when JavaScript from another origin is allowed to read a response.

After this lesson, you will be able to:

1. Determine whether two URLs are **same-origin** or **cross-origin** based on **scheme, hostname, and port**, without confusing them with URL path, DNS aliases, or the concept of "same-site".
2. Describe what SOP protects: JavaScript from one origin cannot by default read sensitive responses from another origin.
3. Explain why a **cross-origin request may have already been sent** even when the browser refuses to let JavaScript read the body; CORS is neither a firewall nor an authentication mechanism.
4. Accurately read `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Expose-Headers`, `Access-Control-Max-Age`, and `Vary`.
5. Distinguish requests that do not require preflight from requests that require an **OPTIONS preflight**; understand the processing order before Spring Security in WebFlux.
6. Configure an origin allowlist scoped properly to `/api/**` using `CorsConfiguration`, `UrlBasedCorsConfigurationSource`, and `ServerHttpSecurity.cors(...)`.
7. Build a working **Java 17+, Spring Boot 3.3.13, WebFlux + Spring Security** example, call the backend from a frontend on a different port, and test with `WebTestClient`.
8. Distinguish **CORS, authentication, authorization, CSRF, and SameSite cookies**; avoid using a wildcard origin with cross-origin credentials.
9. Diagnose errors in browser Network/Console and understand the limitations of testing with curl.
10. Evaluate CORS configurations for development, production, token-based APIs, cookie-based UIs, and reverse proxies.

**One-sentence summary:** SOP is the barrier that restricts reading data across origins in the browser; CORS is a mechanism to **selectively relax that barrier**, not a replacement for any API security control.

## 1. What Is an Origin?

The origin of a URL is typically the tuple:

```text
origin = (scheme, host, port)

URL:    https://api.example.test:8443/v1/orders?status=new
scheme: https
host:   api.example.test
port:   8443

origin: https://api.example.test:8443
```

- **Scheme**: `http` or `https` must match; a different scheme is cross-origin.
- **Host**: hostname must match; `api.example.test` differs from `www.example.test`, and `localhost` differs from `127.0.0.1`.
- **Port**: port must match; `localhost:5173` differs from `localhost:8080`.
- **Path** (`/v1/orders`), query (`?status=new`), and fragment (`#tab`) **do not belong to the origin**.
- For HTTP/HTTPS, default ports are normalized: `https://app.example.test` corresponds to port 443, and `http://app.example.test` corresponds to port 80.
- A URL can have an opaque origin, for example certain cases of `file:`, `data:`, or sandboxed iframes. In such cases the `Origin` header may be `null`; this is **not** a trustworthy hostname to automatically allow.

### 1.1. URL Comparison Table

Suppose JavaScript code runs at `https://app.example.test:443/dashboard`.

| URL called by JavaScript | Same-origin? | Reason |
| --- | --- | --- |
| `https://app.example.test/api/me` | **Yes** | Scheme, host, and normalized port all match |
| `https://app.example.test:443/orders` | **Yes** | Port 443 is the default for HTTPS |
| `https://app.example.test:8443/api/me` | No | Different port |
| `http://app.example.test/api/me` | No | Different scheme; may also hit mixed-content restrictions |
| `https://api.example.test/api/me` | No | Different subdomain/host |
| `https://APP.EXAMPLE.TEST/api/me` | Yes | DNS hostname matching is case-insensitive in normal contexts |
| `https://app.example.test/api/me?x=1` | **Yes** | Different query but origin does not change |
| `https://app.example.test/another/page#top` | **Yes** | Path/fragment do not determine the origin |

**Local example** used throughout this lesson:

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8080

=> Cross-origin because of different PORT, despite the same localhost host name.
```

This is the familiar reason why a Vite/React/Vue frontend calling a Spring Boot backend running on a different port triggers a CORS message in the browser.

### 1.2. Origin Differs from Site

**Same-origin** checks *scheme + host + port*. **Same-site** (in the context of modern cookies) relates to the site by scheme and registrable domain (eTLD+1, with certain exceptions/hostname specifics), and is **not identical to origin**.

For example:

```text
https://app.example.com  -> https://api.example.com

Cross-origin: yes, because the host differs.
Possibly same-site: yes, because scheme and registrable domain match.
```

Therefore, a request can be **cross-origin yet same-site**. A cookie's `SameSite=Lax/Strict/None` policy is a separate concern from JavaScript's permission to read data under CORS.

Do not assume that "two subdomains belonging to the same company" means the browser allows sharing responses by default. Nor should you assume that setting `SameSite=None` on a cookie allows JavaScript to read the response: CORS must still permit the cross-origin request.

## 2. What Does the Same-Origin Policy Protect?

The **Same-Origin Policy** is a browser isolation mechanism: JavaScript from one origin is not allowed by default to access private content served by another origin.

Suppose:

```text
Tab A: https://bank.example (user is logged in)
Tab B: https://malicious.example (JS code controlled by another party)

Tab B runs:
fetch("https://bank.example/api/balance")
```

If Tab B's script could read a response containing banking data without a boundary, merely opening an unfamiliar website would be enough to steal authenticated data from other sites. SOP forces the browser to check permission to **read the response** when the initiator is a different origin.

### SOP Does Not Mean "All Cross-Origin Requests Are Blocked from Being Sent"

Browsers still make many forms of cross-origin requests:

- Users follow links to another website.
- Loading images via `<img src="https://other.example/image.png">`.
- Loading scripts via `<script src="...">` under their respective rules.
- Submitting an HTML form to another URL.
- Sending certain cross-origin `fetch`/XHR requests while **not exposing the response body/headers to JavaScript** if CORS is invalid.

The fact that **a request can reach the server** while **JavaScript is blocked from reading the response** is the most important point. For certain requests that do not require preflight, the server may have already performed a state-changing operation before the browser blocks reading the response.

### What SOP/CORS Does Not Solve

- Does not replace backend authentication/authorization.
- Does not prevent every request sent by a browser, especially a simple form POST.
- Does not block curl, Postman, or backend-to-backend clients: they do not enforce SOP like browser JavaScript.
- Does not protect against CSRF if an API uses cookies; appropriate CSRF/Origin/Fetch Metadata protections are required.
- Does not prevent XSS on the **trusted origin itself**. If `https://app.example.com` has XSS, malicious code runs on an origin that the API already allowlisted.
- Is not a document/user permission system: `Access-Control-Allow-Origin` carries no owner, role, or tenant information.
- Does not govern every protocol: WebSocket handshakes, navigation, iframe embedding, CSP, and postMessage each have their own rules.

**Principle:** CORS decides "JavaScript from which web origin may inspect the response", not "which user may access which resource".

## 3. How Does CORS Work at the HTTP Level?

CORS (**Cross-Origin Resource Sharing**) is the standardized mechanism for the browser and server to negotiate **permission to read a response from another origin**, primarily via HTTP headers.

The browser sends `Origin`:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
```

The server may return:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"message":"public"}
```

The browser compares the calling page's `Origin` against the response's `Access-Control-Allow-Origin` and related conditions. When they match, JavaScript is allowed to access the response under the CORS policy.

**Distinguish two groups of headers:**

| Header | Who sends it? | Purpose |
| --- | --- | --- |
| `Origin` | Browser in the request | Identifies the origin of the environment initiating the request |
| `Access-Control-Request-Method` | Browser, in OPTIONS preflight | Requests permission for the HTTP method to be used |
| `Access-Control-Request-Headers` | Browser, in OPTIONS preflight | Requests permission for non-safelisted request headers to be used |
| `Access-Control-Allow-Origin` | Server response | Specific origin or `*` (subject to conditions) allowed for JavaScript to read |
| `Access-Control-Allow-Methods` | Server, typically in preflight | HTTP methods permitted under CORS |
| `Access-Control-Allow-Headers` | Server, typically in preflight | Request headers allowed to be sent in the actual request |
| `Access-Control-Allow-Credentials` | Server response | Allows the browser to **expose the response of a credentialed request** to JavaScript when all other conditions are met |
| `Access-Control-Expose-Headers` | Server response | Additional response headers JavaScript may read beyond CORS-safelisted ones |
| `Access-Control-Max-Age` | Server, preflight response | Suggests how long the browser may cache the preflight result |
| `Vary: Origin` | Server/proxy | Informs caches that the response may differ depending on the origin |

A response **must not** be written as:

```http
Access-Control-Allow-Origin: https://site-a.test, https://site-b.test
```

to represent a list of origins. The `Access-Control-Allow-Origin` header holds **a single origin** or `*` when valid. The server can configure an allowlist of multiple origins, but the response must select and return the origin matching the request, not concatenate the list into a single value.

### 3.1. Why Is Vary Needed?

If the backend echoes **an allowlisted origin** into `Access-Control-Allow-Origin`, two requests to the same URL from two valid origins can receive different response headers. A CDN/cache that ignores `Origin` could cache the wrong response.

`Vary: Origin` tells caches that the representation/headers depend on `Origin`. For preflight responses, `Vary: Access-Control-Request-Method` and `Vary: Access-Control-Request-Headers` may also be needed depending on the implementation.

**CORS is a per-request/response policy**, so caches, ingress controllers, reverse proxies, or API gateways can break the policy if they inject, strip, or overwrite headers on their own. Test both before and behind the proxy during real deployments.

## 4. Simple Requests and Preflight

### 4.1. Cross-Origin Requests Without Preflight

Example of a GET using only safelisted request headers:

```javascript
fetch("http://localhost:8080/api/public")
  .then(response => response.json())
  .then(data => console.log(data));
```

If the calling page's origin is `http://localhost:5173`, the browser can send the GET immediately. The server must still return a valid `Access-Control-Allow-Origin` for JavaScript to read the JSON. If the CORS header is missing, **the GET may have reached the server** and received HTTP 200, yet `fetch` fails in the browser with a CORS error and JS cannot read the JSON.

The term "simple request" is commonly used for requests that **do not trigger a preflight**. Safelisted conditions include:

- Method is `GET`, `HEAD`, or `POST`.
- No request headers outside the CORS-safelisted list (within their value limits/conditions).
- For a client-set `Content-Type`, only certain safelisted media types such as `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain` (subject to specific conditions).
- Specific features such as `XMLHttpRequest.upload` event listeners or streaming uploads can disqualify a request from being simple; do not memorize only the HTTP method.

**Do not assume "POST always triggers preflight"**: a form POST with a safelisted content type can be sent directly by the browser. That is why CORS cannot replace CSRF protection.

### 4.2. Requests Requiring Preflight

Example of a frontend sending a JSON POST or a request with `Authorization`:

```javascript
fetch("http://localhost:8080/api/private", {
  method: "GET",
  headers: {
    "Authorization": "Basic " + btoa("alice:learn")
  }
});
```

The `Authorization` header is not CORS-safelisted, so the browser typically sends an **OPTIONS preflight** before the actual GET. A `POST` request with `Content-Type: application/json` also typically requires a preflight.

Illustrative preflight request:

```http
OPTIONS /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Successful CORS response:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Demo-Trace
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Header casing, value ordering/spacing, and success status codes may vary by server/browser. This is a **protocol illustration**, not byte-for-byte output from a live run.

If the preflight succeeds, the browser **then sends the actual request**:

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Authorization: Basic <base64-demo-credentials>
```

Preflight is **not used to authenticate users** and, per Fetch/CORS, does not carry credentials such as login cookies in normal scenarios. The browser asks upfront "is this origin allowed to use this method/header?", not "is this user authorized to view /api/private?".

### 4.3. What Happens If Preflight Fails?

The browser does not send the actual request after a disallowed preflight. DevTools Network typically shows OPTIONS blocked, missing `Access-Control-Allow-*`, or an unsuitable 401/403/302 response.

If the actual request was sent but the actual response lacks a valid `Access-Control-Allow-Origin`, JavaScript can still hit a "CORS error" even though the server finished processing. **Inspect both requests** and distinguish:

- `OPTIONS` preflight fails → actual request **is not sent**.
- No preflight, or preflight succeeds but **actual** fails CORS → actual request **may have reached the server**.
- Actual response HTTP 401/403 with valid CORS headers → JavaScript can read status 401/403. This is an authentication/authorization error, **not** a CORS error.

### 4.4. Preflight Cache

`Access-Control-Max-Age` allows the browser to cache the preflight result keyed by the relevant request attributes. The effective duration can be capped by the browser itself, so do not treat 600 seconds as an absolute guarantee. While debugging, a preflight may not appear on every click because it has been cached.

The preflight cache is **not an HTTP cache for the business response**; it only caches the CORS decision for the matching method/headers/origin. Changing `Access-Control-Max-Age` does not make login tokens live longer.

## 5. CORS Differs from Authentication, Authorization, and CSRF

### 5.1. A Quick Summary Table

| Mechanism | Question it answers | Primary enforcement |
| --- | --- | --- |
| **Same-Origin Policy** | May JS from this origin read data from another origin by default? | Browser |
| **CORS** | From which origin, and with which methods/headers/credentials, does the server let JS read the response? | Browser checks headers returned by server |
| **Authentication** | Who is this, and have credentials/tokens been verified? | Backend/Spring Security |
| **Authorization** | What may this principal do with which resource? | Backend/Spring Security and service/domain |
| **CSRF protection** | Can a browser carrying cookies be tricked by another website into sending state-changing requests? | Server + token/Origin/Fetch Metadata/cookie policy |
| **Cookie SameSite** | Will the browser send the cookie in this cross-site context? | Browser |
| **CSP (Content Security Policy)** | Where is the page allowed to load/execute content from or connect to? | Browser enforces the page's policy |
| **TLS/HTTPS** | Is data protected in transit? | Client–server transport |

### 5.2. CORS Does Not Block curl

`curl` has no browser SOP mechanism. An attacker can still run:

```bash
curl -i -H 'Origin: https://evil.example' \
  http://localhost:8080/api/private
```

An attacker can even **spoof the Origin header** in a non-browser client. Therefore, **never treat `Origin` as proof that the caller is trusted or authorized**. The backend must verify sessions/tokens/roles/resources as usual.

A valid `Access-Control-Allow-Origin` does not prove a request is authorized either. For `/api/private`, Spring Security still requires authentication. Conversely, a browser request blocked by CORS may already have been processed by the backend even if the caller cannot read the response.

### 5.3. CORS Does Not Replace CSRF Protection

An untrusted website can send certain simple cross-origin POSTs or form submissions carrying cookies depending on browser rules. SOP can prevent **reading the response**, but **does not roll back side effects** that already occurred. If an API uses cookies/sessions to identify the browser, the server needs CSRF protection for state-changing operations as appropriate, and cookie policies help reduce risk.

In Spring Security WebFlux, `CsrfWebFilter` protects the necessary requests according to configuration. **Do not enable CORS and blindly disable CSRF.** For header-only Bearer APIs, the CSRF risk differs, but you must evaluate how credentials are sent (cookies, Basic, automatic vs. explicit tokens), not rely on the label "REST".

### 5.4. You Can Still Get 401/403 Even With CORS Enabled

Suppose a frontend from `http://localhost:5173` calls `GET /api/private`. The backend returns:

```http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: http://localhost:5173
WWW-Authenticate: Basic ...
```

This is valid: CORS lets JavaScript **see the 401 status**, without creating an Authentication. If the user is authenticated but lacks the required role, the response may be 403. The browser must be allowed to read error responses under CORS if the frontend needs to handle those status codes explicitly.

## 6. Credentialed Requests: Cookies, Authorization, and Wildcards

### 6.1. Fetch Credentials Mode

In `fetch()`, `credentials` controls when the browser sends browser-managed credentials (especially cookies and HTTP auth state) and processes `Set-Cookie`. Common values:

- `same-origin`: default; automatically sends credentials for same-origin requests, does not automatically send cross-origin cookies like `include`.
- `include`: allows sending credentials even cross-origin **if cookie policies, SameSite/Secure, browser privacy settings, and other conditions allow it**.
- `omit`: does not use browser-managed credentials.

Example of a UI using a session cookie across origins:

```javascript
fetch("https://api.example.test/api/me", {
  credentials: "include"
});
```

For JavaScript to read the response of a cross-origin credentialed request, the backend needs:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

**Do not use**:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

for requests requiring credentials. The browser will refuse to expose the response to JavaScript. The server must return **a specific allowed origin**. Spring's `CorsConfiguration` also disallows combining `allowedOrigins("*")` with `allowCredentials(true)` in standard configuration.

### 6.2. Explicitly Set Authorization Header

A frontend can explicitly set `Authorization: Bearer ...` or Basic for an API. That header is not safelisted, so it usually triggers a preflight and must appear in CORS `allowedHeaders`.

```javascript
fetch("https://api.example.test/api/me", {
  headers: {
    "Authorization": "Bearer " + token
  },
  credentials: "omit"
});
```

This is an **explicit** token mechanism, not automatic cookies. The browser still enforces CORS on the cross-origin request, and preflight is needed for the `Authorization` header. `Access-Control-Allow-Credentials` specifically pertains to **credentials mode include**; you cannot use it as a check for whether a Bearer token is valid.

Tokens should not be embedded in public frontend source code, arbitrary `localStorage`, or URL query parameters; design token storage and OAuth2 flows according to your threat model. The snippet above only illustrates the HTTP mechanism.

### 6.3. SameSite Cookies and Third-Party Cookies

Even when the backend returns `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials: true`, the browser may still **refuse to send cookies**, for example:

- The cookie is restricted by `SameSite=Lax` or `Strict` in a cross-site context;
- The cookie needs `SameSite=None; Secure` to participate in certain cross-site requests over HTTPS;
- The browser blocks third-party cookies under its privacy settings;
- The cookie has the wrong `Domain`/`Path`, is expired, or the frontend/backend differ in hostname/scheme;
- The request does not use `credentials: "include"` even though the backend expects a cookie.

`SameSite=None; Secure` is not a recommendation to enable on every cookie: it widens cross-site exposure and requires CSRF protection, HTTPS, and product-level review. For two subdomains on the same site but different origins, CORS is still mandatory for browser JS to read the response, even if SameSite does not necessarily block the cookie.

### 6.4. Exposing Response Headers

JavaScript cannot automatically read all cross-origin response headers even when CORS allows reading the body. If the server returns:

```http
X-Server-Variant: webflux-demo
Access-Control-Expose-Headers: X-Server-Variant
```

only then can JS read:

```javascript
const version = response.headers.get("X-Server-Variant");
```

Certain CORS-safelisted response headers are readable by default, while custom headers must be exposed. **`Set-Cookie` cannot be exposed to JavaScript via `Access-Control-Expose-Headers`** because it is a forbidden response-header name; the browser can process the cookie, but JS cannot directly read that header's contents.

## 7. CORS in Spring WebFlux and Spring Security Reactive

### 7.1. HandlerMapping, @CrossOrigin, and CorsWebFilter

Spring WebFlux supports CORS in multiple places:

1. `@CrossOrigin` on an annotated controller or method.
2. `WebFluxConfigurer.addCorsMappings(...)` configuration at `HandlerMapping`.
3. `CorsWebFilter` handling CORS at the filter layer.
4. `ServerHttpSecurity.cors(...)` integrating the CORS filter into the **Spring Security WebFlux chain** at the appropriate position.

In an application with Spring Security enabled, **preflight must be handled before the authentication step**. If an `OPTIONS` request carries no session cookie/Authorization and security requires authentication before CORS runs, the preflight can receive a 401 or redirect, preventing the browser from sending the actual request.

The Spring Security reactive documentation recommends using `CorsWebFilter` or CORS integration via `CorsConfigurationSource`; `ServerHttpSecurity.CorsSpec.configurationSource(...)` ensures the filter is inserted at the right order in the security chain.

### 7.2. One Configuration Source, One Clear Place of Enforcement

Choose one strategy:

- **Inside the security chain:** `.cors(spec -> spec.configurationSource(source))` using a `UrlBasedCorsConfigurationSource` bean; this is the primary choice in our example.
- **Global filter:** a `CorsWebFilter` bean ordered appropriately ahead of Spring Security if your application architecture requires it.
- **HandlerMapping-only:** `@CrossOrigin` or `WebFluxConfigurer` can fit applications without security preflight blocking, but must be verified against Spring Security integration.

**Do not blindly declare both a global `CorsWebFilter` and `.cors(...)` using the same policy** without understanding filter ordering and response header duplication. With multiple `SecurityWebFilterChain`s, the CORS source/matcher must cover all endpoints requiring cross-origin access; if a preflight hits a chain without CORS support, the frontend will still fail.

### 7.3. Configuration Types Must Match the Reactive API

| Purpose | WebFlux reactive | Servlet MVC |
| --- | --- | --- |
| Security DSL | `ServerHttpSecurity` | `HttpSecurity` |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| CORS filter | `org.springframework.web.cors.reactive.CorsWebFilter` | `org.springframework.web.filter.CorsFilter` |
| CORS source | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.UrlBasedCorsConfigurationSource` |
| Request context | `ServerWebExchange` | `HttpServletRequest` |
| CORS config object | `org.springframework.web.cors.CorsConfiguration` | `org.springframework.web.cors.CorsConfiguration` |

**An especially dangerous import mistake:** Both packages contain a class named `UrlBasedCorsConfigurationSource` with different types. For `ServerHttpSecurity.CorsSpec.configurationSource(...)`, you must use the **reactive** `CorsConfigurationSource`. If your IDE auto-imports the Servlet class, the code may fail to compile or lead to a misconfigured model.

## 8. Runnable Java 17+ Example: Backend 8080 and Frontend 5173

We will create:

- A Spring Boot WebFlux backend at `http://localhost:8080`.
- A simple HTML/JavaScript frontend at `http://localhost:5173`.
- CORS allowed only from `http://localhost:5173`, scoped to `/api/**`.
- Cross-origin cookies disallowed (`allowCredentials=false`) in the basic demo.
- Allowed methods `GET`/`POST`/`OPTIONS`, and headers `Authorization`, `Content-Type`, and `X-Demo-Trace`.
- `GET /api/public` is public, `GET /api/private` requires HTTP Basic, and `POST /api/changes` requires authentication while still keeping default CSRF protection enabled.
- Tests for CORS *and* authorization/CSRF separately, proving CORS is not a security permission.

### 8.1. Project Structure

```text
sop-cors-webflux/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/SopCorsApplication.java
    test/
      java/example/SopCorsApplicationTests.java
  client/
    index.html
```

Create `settings.gradle`:

```groovy
rootProject.name = 'sop-cors-webflux'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add Servlet's `spring-boot-starter-web`. The Spring Boot BOM provides Spring Security, Reactor, and Spring Framework versions aligned with Boot 3.3.13. This lesson pins versions so the example is easy to reproduce; real production applications must stay updated according to support lifecycles and security advisories.

### 8.2. Backend: SopCorsApplication.java

Create `src/main/java/example/SopCorsApplication.java`:

```java
package example;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SopCorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SopCorsApplication.class, args);
    }

    @GetMapping("/api/public")
    public ResponseEntity<Map<String, String>> publicData() {
        return ResponseEntity.ok()
                .header("X-Server-Variant", "webflux-demo")
                .body(Map.of("message", "PUBLIC_OK"));
    }

    @GetMapping("/api/private")
    public ResponseEntity<Map<String, String>> privateData() {
        return ResponseEntity.ok()
                .header("X-Server-Variant", "webflux-demo")
                .body(Map.of("message", "PRIVATE_OK"));
    }

    @PostMapping("/api/changes")
    public Map<String, String> changeData() {
        // Purpose: demonstrate that CSRF remains active.
        // No real data is mutated in this demo.
        return Map.of("message", "CHANGED");
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Trust only the exact origin of the demo frontend.
        config.setAllowedOrigins(List.of(
                "http://localhost:5173"));

        // CORS method allowance does not grant backend authorization.
        config.setAllowedMethods(List.of(
                "GET", "POST", "OPTIONS"));

        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Demo-Trace"));

        config.setExposedHeaders(List.of(
                "X-Server-Variant"));

        // Demo uses an Authorization header, not cookies
        // over cross-origin fetch with credentials: include.
        config.setAllowCredentials(false);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
                // Place CorsWebFilter at the right position in the security chain.
                .cors(spec -> spec.configurationSource(corsSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/api/public")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/private")
                        .authenticated()
                        .pathMatchers(
                                HttpMethod.POST, "/api/changes")
                        .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Do not disable CSRF for POST /api/changes.
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

**Design explanation:**

1. `corsConfigurationSource()` defines an **exact** origin allowlist. There is no `*`, and the request `Origin` is never treated as a trusted identity.
2. `registerCorsConfiguration("/api/**", config)` applies the CORS configuration only to API paths. Other endpoints are not automatically opened to the frontend.
3. `.cors(spec -> spec.configurationSource(corsSource))` integrates CORS into the Spring Security WebFlux chain and handles preflight before authorization steps that require a user. Do not create a second global `CorsWebFilter`.
4. `setAllowedHeaders(...)` must include `Authorization` so preflights for Basic/JWT fetches are accepted, and `Content-Type` for JSON POSTs.
5. `setExposedHeaders(...)` lets JS read the `X-Server-Variant` header in cross-origin responses; it does not grant endpoint access.
6. `setAllowCredentials(false)` demonstrates an API that does not use browser cookies across origins, sending only an explicit Basic header in the demo. Do not use `credentials: "include"` on the client and expect the server to comply without enabling credentialed CORS.
7. `/api/public` returns 200 without login. `/api/private` still requires valid HTTP Basic credentials, even when the origin is allowlisted.
8. `POST /api/changes` exists, while CSRF **remains enabled**. A POST request with valid Basic credentials and valid CORS but missing a CSRF token can still receive **403**. This proves CORS does not bypass CSRF.
9. `{noop}learn` is only local learning data; real applications must use an appropriate password encoder, TLS/HTTPS, and a suitable authentication mechanism.
10. Do not add `@CrossOrigin("*")` on controllers after configuring a centralized source without evaluating how policies combine.

### 8.3. Frontend index.html

Create `client/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Same-Origin Policy and CORS Demo</title>
</head>
<body>
  <h1>Frontend localhost:5173 → WebFlux localhost:8080</h1>
  <p>This example uses a local demo account only.</p>

  <button id="public">Public GET</button>
  <button id="private">GET with Basic Authorization</button>
  <button id="post">POST JSON (CSRF still enabled)</button>

  <pre id="output" aria-live="polite"></pre>

  <script>
    const base = "http://localhost:8080";
    const output = document.getElementById("output");

    async function run(path, options) {
      output.textContent = "Calling " + path;
      try {
        const response = await fetch(base + path, options);
        const body = await response.text();
        const variant = response.headers.get("X-Server-Variant");

        output.textContent = JSON.stringify({
          status: response.status,
          ok: response.ok,
          variant: variant,
          body: body
        }, null, 2);
      } catch (error) {
        output.textContent =
            "Fetch failed; check DevTools Network/Console: "
            + String(error);
      }
    }

    document.getElementById("public").onclick = () =>
      run("/api/public", { method: "GET" });

    document.getElementById("private").onclick = () =>
      run("/api/private", {
        method: "GET",
        headers: {
          "Authorization": "Basic " + btoa("alice:learn")
        }
      });

    document.getElementById("post").onclick = () =>
      run("/api/changes", {
        method: "POST",
        headers: {
          "Authorization": "Basic " + btoa("alice:learn"),
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ action: "demo" })
      });
  </script>
</body>
</html>
```

Never put real usernames or passwords into JavaScript delivered to the browser. `btoa("alice:learn")` only demonstrates the browser sending `Authorization` from a learning frontend; it **does not protect credentials**. Production apps should use a properly designed login/token flow and never hardcode secrets or Basic passwords in JS.

### 8.4. Running the Two Origins

Terminal 1, from the project directory:

```bash
gradle bootRun
```

If you have the Gradle Wrapper, use `./gradlew bootRun` or `gradlew.bat bootRun`.

Terminal 2: if Python 3 is installed, run:

```bash
python3 -m http.server 5173 --directory client
```

On Windows with the Python Launcher, you can run `py -m http.server 5173 --directory client`. If Python is not installed, use another static development server to serve `client/index.html` on `http://localhost:5173`; do not open the file via `file://` because the opaque origin behaves differently.

Open the browser at `http://localhost:5173`, open DevTools → Network → Preserve log. Click the three buttons in order:

| Button | Preflight? | Expected actual request | JavaScript outcome |
| --- | --- | --- | --- |
| Public GET | Not needed in this example | GET `/api/public` | Reads 200, `PUBLIC_OK`, `X-Server-Variant` |
| GET with Basic | Yes, due to `Authorization` header | GET `/api/private` with valid Basic auth | Reads 200, `PRIVATE_OK` |
| POST JSON | Yes, due to JSON Content-Type and Authorization | POST `/api/changes` | Typically reads status **403** due to CSRF, not CORS |

If the actual request receives a 401/403 error **with valid CORS headers**, JS can still access `response.status`. In the Fetch API, HTTP 4xx/5xx responses **do not reject the Promise**; they resolve to a `Response` with `ok=false`. The Promise rejects only on network-level/CORS failures and other fetch errors. This distinction is critical when debugging frontends.

**Demo scope note:** The 403 on POST relies on Spring Security's default CSRF protection and sending a request without a token; the example does not attempt to acquire and submit a CSRF token, as full session/login CSRF workflows are covered outside this lesson.

## 9. Testing the Backend with WebTestClient

Create `src/test/java/example/SopCorsApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SopCorsApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void allowedOriginCanReadPublicEndpoint() {
        client.get().uri("/api/public")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173")
                .expectHeader().valueEquals(
                        "X-Server-Variant", "webflux-demo")
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS)
                .expectBody()
                .jsonPath("$.message").isEqualTo("PUBLIC_OK");
    }

    @Test
    void preflightForAuthorizationHeaderWorksWithoutLogin() {
        client.options().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173")
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void unlistedOriginPreflightIsRejected() {
        client.options().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "https://untrusted.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization")
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void allowedOriginStillNeedsAuthentication() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "http://localhost:5173");
    }

    @Test
    void validBasicCredentialsAllowPrivateResource() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PRIVATE_OK");
    }

    @Test
    void postCanPassCorsButFailCsrf() {
        client.post().uri("/api/changes")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sameOriginStyleRequestWithoutOriginStillWorks() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PUBLIC_OK");
    }
}
```

Run:

```bash
gradle test
```

**What the tests prove:**

- The configuration permits origin `localhost:5173` for public GETs and preflights with the `Authorization` header.
- Preflight **does not require a logged-in account**; if challenged with 401, inspect the CORS filter position.
- An origin not on the allowlist is rejected on OPTIONS and receives no `Access-Control-Allow-Origin`.
- `GET /api/private` still requires HTTP Basic: CORS success **does not** imply authorization success.
- `POST /api/changes` without a CSRF token still returns 403; allowing POST in CORS does not disable CSRF.
- Requests without an `Origin` header work normally as standard HTTP requests.

**WebTestClient limitation:** It is not a browser and does not enforce the **Same-Origin Policy** in JS. It only sends headers and inspects backend responses. Therefore, you must also test in Chrome/Firefox with a real frontend to confirm browser fetch and preflight behavior.

## 10. Manual Testing with curl: Reading the Results Properly

### 10.1. Simple GET with Valid Origin

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/public
```

You expect HTTP 200 and headers:

```http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: X-Server-Variant
```

### 10.2. OPTIONS Preflight

```bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  http://localhost:8080/api/private
```

Expect the preflight to be handled by the CORS filter with `Access-Control-Allow-Origin` and `Access-Control-Allow-Methods`/`Headers`. **Do not** add `Authorization` to the preflight; this is not the actual request.

### 10.3. Disallowed Origin

```bash
curl -i -X OPTIONS \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  http://localhost:8080/api/private
```

The demo's `CorsWebFilter` configuration rejects invalid preflights, typically with 403. In a browser, the actual request is not sent after a rejected preflight. When testing with `curl`, you only see the server response; it **does not prove the browser prevented a script from reading the body**.

### 10.4. CORS OK, Yet Security Still Requires Auth

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private

curl -i -u alice:learn \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private
```

The first command expects a 401 Basic challenge, the second 200. Both can include CORS headers allowing the allowlisted frontend to observe the HTTP status, but only the second has valid credentials.

**Crucial note:** `curl` can set any `Origin` and read the response regardless of `Access-Control-Allow-Origin`. Never conclude CORS works in a browser just because curl read the response. Inspect the headers, then verify in a real browser.

### 10.5. Wrong Frontend URL

If you run the frontend server at `http://127.0.0.1:5173` while the backend only allows `http://localhost:5173`, that is a **different origin** because the hostname differs; preflight can fail. Use the exact URL across all tests. Ports 5173 and 8080 are intentionally different.

## 11. CORS Policy Matrix

| Scenario | CORS | Authentication / CSRF | Expected Outcome |
| --- | --- | --- | --- |
| Public GET from allowlisted origin | Allowed | No auth required | JavaScript reads 200 |
| Public GET from other origin | Browser blocks JS read | Handler may still run depending on request type | CORS error in browser; actual may reach server |
| Private GET from allowlisted origin, no credentials | Allowed for origin | Unauthenticated | JS reads 401/challenge per policy |
| Private GET from allowlisted origin, valid Basic | Preflight/actual CORS OK | Authenticated | JS reads 200 |
| JSON POST from allowlisted origin, missing CSRF | Preflight OK | Rejected by CSRF | JS reads 403 if actual has valid CORS headers |
| Credentialed cookie request with ACAO `*` | Browser refuses read | Backend session may still work | CORS failure; invalid configuration |
| Credentials include with specific ACAO + ACAC true | Browser exposes response if cookie policy also permits | Backend still enforces authn/authz/CSRF | Depends on policy, not automatically 200 |
| curl with arbitrary Origin | curl does not enforce SOP | Backend auth applies | curl reads response as an HTTP client |
| Browser same-origin | No cross-origin CORS negotiation needed | Auth/CSRF still apply | Depends on backend policy |
| Browser request fails at preflight | OPTIONS rejected | Actual not sent | JS receives CORS/network error |
| Browser GET sent, actual missing ACAO | Actual may have reached backend | Side effects (if any) are not rolled back | JS cannot read response |

Do not mechanically guess the HTTP status from the browser console alone. For example, a CORS failure typically appears as a **network error** to the Fetch API, even though the Network tab shows HTTP 403 on preflight or 200 on actual. When CORS is valid and the backend returns 401, JS receives a `Response` with `status=401`; that is a different situation.

## 12. When to Use allowedOrigins("*") and When Not To?

### 12.1. Truly Public Data Without Credentials

For non-sensitive public resources meant to serve any website, `Access-Control-Allow-Origin: *` can be a valid choice when requests do not use credentials mode `include` and the server genuinely intends every origin to read the response.

For example, a public lookup API (no users, no cookies/sessions, no internal data) can use a wildcard after evaluating quotas and abuse risks. **A CORS wildcard does not turn a private API into a public one**, though if authentication is weak or an endpoint leaks data, allowing all sites to read the response increases exposure.

### 12.2. APIs with Cookies/Sessions or User Data

If credentials are allowed, **do not use** `allowedOrigins("*")`. Choose an explicit allowlist:

```java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of(
        "https://app.example.test",
        "https://admin.example.test"));
config.setAllowCredentials(true);
```

This is an **illustrative snippet**, not a complete demo configuration; to run it, import `CorsConfiguration`, `List`, and register the appropriate source/filter.

With credentials, echoing an origin validated against an allowlist is very different from **unconditionally echoing any Origin**:

```java
// VERY DANGEROUS: every incoming origin becomes an allowed origin.
config.addAllowedOriginPattern("*");
config.setAllowCredentials(true);
```

`allowedOriginPatterns` can be used when controlled patterns are genuinely needed (for example, an organization-owned list of subdomains), as Spring includes logic to reflect the matched origin. However, combining the `*` pattern with credentials effectively opens access to every origin and creates serious risk when an API relies on session cookies. Do not use it as a "wildcard error workaround" without a threat model.

### 12.3. Mixing Development and Production Environments

Allowlist only the exact real origins for each environment:

```text
dev:     http://localhost:5173
staging: https://staging-app.example.test
prod:    https://app.example.test
```

Do not leave `http://localhost:5173` in production unnecessarily, and do not configure `allowedOriginPatterns("https://*.example.test")` when third parties can control subdomains. For APIs with credentials, **every origin in the allowlist is part of your trust boundary**, so you must control who can deploy JavaScript on that origin.

## 13. Common Issues in Spring Security Reactive

### 13.1. OPTIONS Receives 401 Before Reaching the Controller

**Symptom:** DevTools shows `OPTIONS /api/private` returning 401, and the frontend reports preflight failure.

**Cause:** Security processes the preflight as an unauthenticated request before CORS is handled.

**Fix:** Use `CorsConfigurationSource` and integrate `.cors(spec -> spec.configurationSource(source))`, or a properly ordered global `CorsWebFilter`. Simply adding `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` is not enough; the browser still requires **valid CORS response headers** on the preflight.

### 13.2. Public GET Returns HTTP 200 Yet Browser Reports a CORS Error

The actual response may be missing `Access-Control-Allow-Origin` or its value may not match `Origin`. Inspect the response of the **actual GET** as well, not just the preflight. CORS headers are also needed on error responses if the frontend needs to inspect their status.

### 13.3. Browser Reports "blocked by CORS" Yet Backend Logs Show the Request Ran

No contradiction. A simple request can still be sent; the browser only blocks JavaScript from reading the response. This matters especially for state-changing POSTs: never use CORS as a CSRF defense.

### 13.4. Configuring Only @CrossOrigin on the Controller

Preflight can be blocked by Spring Security **before** the request reaches `HandlerMapping`; `@CrossOrigin` will not rescue every setup. Verify that CORS is integrated early and test uncredentialed `OPTIONS` requests.

### 13.5. Importing the Wrong Package for CorsConfigurationSource

For WebFlux:

```java
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

**Do not** import Servlet's `org.springframework.web.cors.UrlBasedCorsConfigurationSource` when using `ServerHttpSecurity.CorsSpec`.

### 13.6. Mismatched Origins That Look Similar

`http://localhost:5173`, `http://127.0.0.1:5173`, `https://localhost:5173`, and `http://localhost:5174` are all different origins. Host, scheme, and port must match. Check the actual `Origin` header sent by the browser.

### 13.7. Bearer Authorization Rejected During Preflight

The `Authorization` header is missing from `allowedHeaders`, or the method is not yet in `allowedMethods`. Inspect `Access-Control-Request-Headers: authorization` in `OPTIONS` and `Access-Control-Allow-Headers` in the response.

### 13.8. Valid CORS Yet Cookies Are Not Sent with Requests

Distinguish `credentials: "include"`, cookie `SameSite`/`Secure`/`Domain`/`Path`, browser third-party cookie settings, and backend policies. Having `Access-Control-Allow-Credentials: true` does not force the browser to send cookies if the cookie is not permitted to be sent.

### 13.9. Browser Rejects Credentialed CORS With a Wildcard

`Access-Control-Allow-Origin: *` is invalid when a request uses credentials mode `include`. Return the exact origin after an allowlist check alongside `Access-Control-Allow-Credentials: true`; do not open `allowedOriginPatterns("*")` just to dodge the error at the expense of your trust boundary.

### 13.10. CORS Applied Twice

Creating a global `CorsWebFilter` bean while also enabling `ServerHttpSecurity.cors(...)` with another source can produce duplicate headers, conflicting policies, or hard-to-debug failures. Choose one clear strategy, check filter ordering, and test both actual and preflight responses.

### 13.11. Frontend Using mode: no-cors as a "Fix"

```javascript
fetch("http://localhost:8080/api/public", {
  mode: "no-cors"
});
```

This typically yields an **opaque response** whose status/body/headers JavaScript cannot read like a normal CORS response. This is not how to consume a JSON API. Fix the server's origin policy properly instead of turning off browser visibility.

### 13.12. Server Returns a 302 Redirect for Preflight

Preflight may be redirected to a login page, causing the browser to abort the actual request or fail depending on the case. Handle CORS **before** authentication; if your frontend is an SPA calling an API, prefer a security chain with 401 JSON/Bearer semantics instead of HTML redirects for API requests.

### 13.13. Reverse Proxy/CDN Injects Headers Indiscriminately

Ingress/nginx/gateway layers might:

- Add `Access-Control-Allow-Origin: *` to every response;
- Overwrite Spring Boot's allowlist;
- Strip `Vary: Origin` or cache responses under the wrong key;
- Omit proper CORS headers on 401/403/5xx responses;
- Fail to forward `OPTIONS` to the backend or return inconsistent preflights themselves.

Decide on **one layer to manage CORS** (the gateway or the application) with a clear contract and end-to-end tests; do not let two layers independently reflect origins without coordination.

### 13.14. Allowing Origin null Without Careful Thought

Requests with `Origin: null` can come from opaque origins such as sandboxed iframes or file URLs. Do not treat `null` as "no Origin". If a specialized application requires it, use authentication and an allowlist backed by a clear threat model—never allow `null` merely because a local frontend was opened via `file://`.

### 13.15. CORS Path Pattern Does Not Match Backend Route

Configuration covers only `/api/**`, while actual requests go to `/graphql`, `/oauth/token`, `/actuator/**`, or paths rewritten by a proxy. If the CORS source does not match, the browser may not receive the expected headers. Open only the endpoints that need cross-origin access, and verify the path WebFlux actually sees behind any reverse proxy.

### 13.16. CORS Allows a Method, Yet the Route Does Not Exist

Allowing `POST` in preflight does not generate a `@PostMapping` or grant authorization. The backend can return 404/405/403 after the actual request runs. Verify authorization, CSRF, routing, and validation separately.

## 14. Practical Design Scenarios

### 14.1. SPA Calling an API with Bearer JWT

```text
SPA: https://app.example.test
API: https://api.example.test
Auth: Authorization: Bearer <token>
```

Allowlist the exact SPA origin and permit the `Authorization` header and required methods. Preflight does not carry the Bearer token; the resource server verifies the JWT on the **actual request**. Keep CORS policy separate from JWT issuer/audience/scope validation. Do not confuse the CORS allowlist with the set of clients authorized to obtain tokens.

If the frontend does not use browser-managed cookies, `Access-Control-Allow-Credentials: true` may not be needed. Still, evaluate where tokens are stored and XSS risk; do not treat "Bearer-only" as an excuse to drop other defenses.

### 14.2. SPA Using Cookie Sessions

```text
SPA: https://app.example.test
API: https://api.example.test
Session: Cookie
```

Requirements typically include:

- Specific SPA origin CORS allowlist;
- `Access-Control-Allow-Credentials: true`;
- `fetch(...,{credentials:"include"})` when the browser must send cookies cross-origin;
- Appropriate `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` cookie policies;
- CSRF token or equivalent defense for state-changing operations;
- User- and resource-level authorization;
- HTTPS and session fixation/logout/timeout controls per policy.

This design is more sensitive than a public GET. **Never fix CORS while forgetting CSRF or cookie security.**

### 14.3. Backend-to-Backend or curl

Service-to-service calls via `WebClient` are not subject to browser SOP; CORS does not authorize server-side HTTP clients. Use mTLS, OAuth client credentials, network policies, or other authentication. If a `WebClient` gets 401/403, fix authentication/authorization—do not enable CORS for it.

### 14.4. Public API with Rate Limiting

`Access-Control-Allow-Origin: *` lets browser JS from any origin read public responses, but **does not limit call volume** and does not replace quotas, rate limiting, or abuse detection. Apply rate limits by API key/user/IP appropriately and guard against enumeration/scraping.

### 14.5. Multiple SecurityWebFilterChains

`WebFilterChainProxy` selects the first matching chain. If the `/api/**` Bearer chain has CORS configured while the `/app/**` UI chain does not, a cross-origin frontend hitting `/app/**` can fail. For every chain, check:

1. Does `securityMatcher` cover both the actual URL and `OPTIONS`?
2. Is CORS processed before authentication?
3. Does `CorsConfigurationSource` map the right paths?
4. Do `authorizeExchange` rules and the HTTP entry point return appropriate statuses for APIs?
5. Does chain precedence accidentally route requests into the wrong chain?

Do not assume a single `@CrossOrigin` on one controller fixes all security chains.

## 15. Systematic Debugging with DevTools

### Step 1: Confirm the Actual Origin

In Console:

```javascript
console.log(window.location.origin);
```

Record the exact scheme/host/port and compare it against `setAllowedOrigins(...)`. Do not compare only the parent domain.

### Step 2: Check Whether OPTIONS Exists

In Network, filter for `OPTIONS` and the API path. If a preflight is present, inspect:

```text
Request Headers:
  Origin
  Access-Control-Request-Method
  Access-Control-Request-Headers

Response Headers:
  Access-Control-Allow-Origin
  Access-Control-Allow-Methods
  Access-Control-Allow-Headers
  Access-Control-Allow-Credentials (when needed)
  Access-Control-Max-Age
  Vary
```

If `OPTIONS` receives 401 or a redirect, check CORS/security ordering. If it returns 403 because the Origin/method/header is disallowed, adjust the **exact allowlist** rather than opening wildcards indiscriminately.

### Step 3: Inspect the Actual Response

If `OPTIONS` succeeds, verify whether the **actual GET/POST** was sent, what status it returned, and whether the response includes ACAO. If actual returns 401/403 with valid CORS headers, switch to debugging tokens/sessions/roles/CSRF—it is no longer a browser-level CORS permission issue.

### Step 4: Check Fetch Credentials and Cookies

If the backend relies on sessions, check `credentials: "include"`, cookie policy, SameSite/Secure, host/path, and `Set-Cookie`. Do not assume cookies were sent just by looking at `Access-Control-Allow-Credentials`.

### Step 5: Distinguish Browser from curl

Reproduce `OPTIONS` with curl to inspect backend configuration, but **test in a real browser** to confirm SOP behavior. Reading a response with curl does not prove JavaScript can read it.

### Step 6: Inspect Proxies and Caches

If local works but production fails, inspect nginx/ingress/CDN layers, duplicated CORS headers, path rewrites, and `Vary`. Avoid changing both Spring Boot and the gateway at the same time without knowing which layer emits the CORS headers.

### Step 7: Test Negative Cases

- Origin not in the allowlist;
- Origin with a different port or scheme;
- Disallowed request header;
- Disallowed request method;
- Credentialed request with wildcard;
- Unauthorized user with valid CORS;
- POST missing CSRF;
- API 500 error with proper CORS/error handling if the frontend needs to read error statuses.

**Negative tests matter as much as positive tests**, because an overly permissive CORS policy "works" functionally while exposing data to untrusted origins.

## 16. Pre-Deployment Checklist

1. **Exact origins:** configure scheme+host+port per environment; avoid lookalike hostnames.
2. **Restrict paths:** enable CORS only for needed endpoints, e.g., `/api/**`; do not expose all Actuator/admin endpoints by default.
3. **Allowed methods/headers:** permit only actually needed methods/headers; list `Authorization` and `Content-Type` when used.
4. **Expose headers:** expose only what the frontend needs; `Set-Cookie` cannot be exposed to JS.
5. **Credentials:** enable `allowCredentials(true)` only when genuinely required, and never combine `allowedOrigins("*")` with credentials.
6. **Cookies/CSRF:** review SameSite, Secure, HttpOnly, Origin/Fetch Metadata/CSRF tokens, and HTTPS for session-based apps.
7. **Filter ordering:** handle preflight before authentication so it does not hit unnecessary 401/302 responses.
8. **Single source of policy:** avoid conflicting CORS headers across WebFlux, Spring Security, and proxies.
9. **Separate authorization:** CORS does not replace permission/role/resource-owner/tenant checks.
10. **Error responses:** ensure 401/403/5xx responses carry proper CORS headers when the client is allowed to read them; never leak stack traces or secrets.
11. **Caching:** ensure `Vary: Origin` and suitable preflight caching; test behind your CDN.
12. **Non-browser clients:** curl and backend-to-backend callers must still be authenticated; never trust a client-supplied Origin header.
13. **Observability:** monitor preflight allows/denies, invalid Origins, authentication failures, CSRF failures, and HTTP errors separately.
14. **Least privilege:** do not add `@CrossOrigin("*")` or `allowedOriginPatterns("*")` just to silence console errors.
15. **Browser tests:** verify dev/prod frontends in real browsers rather than relying solely on `WebTestClient`.
16. **Upgrades:** verify Spring Security WebFlux APIs for your Boot version, especially reactive CORS packages and multiple filter chains.

## 17. Self-Check Questions

**1. Are `http://localhost:5173` and `http://localhost:8080` same-origin?**  
No, because the ports differ, even with the same hostname.

**2. Does changing `/api/a` to `/api/b` on the same server change the origin?**  
No. Paths are not part of the origin tuple.

**3. Does SOP forbid sending all cross-origin requests?**  
No. Many requests can still be sent; SOP/CORS primarily restricts JavaScript from reading cross-origin responses.

**4. If CORS lets the frontend read `/api/private`, does that mean the user is authorized to view the data?**  
No. Spring Security still enforces authentication and authorization; the request can still receive 401/403.

**5. When does an OPTIONS preflight occur?**  
When a cross-origin request is not safelisted, such as carrying an `Authorization` header or sending a JSON POST with `Content-Type: application/json`.

**6. Does preflight use the actual request's session cookie or Bearer token to prove permissions?**  
Per the Fetch specification, CORS preflights do not carry credentials; they check origin/method/headers upfront and do not replace authentication on the actual request.

**7. If the browser blocks reading the response of a simple POST, could the server have already modified data?**  
Yes. That is why CORS does not replace CSRF protection.

**8. Is a CORS request with credentials mode `include` valid alongside `Access-Control-Allow-Origin: *`?**  
No. A specific allowed origin and `Access-Control-Allow-Credentials: true` are required.

**9. Why does `Vary: Origin` matter for CDNs?**  
Because response headers can vary by `Origin`; a cache missing `Vary` could mistakenly reuse the wrong CORS policy.

**10. Does `Access-Control-Expose-Headers` let JS read `Set-Cookie`?**  
No. `Set-Cookie` is a forbidden response-header name under Fetch.

**11. Does enabling `@CrossOrigin` on a controller guarantee preflights pass Spring Security properly?**  
No. CORS must be integrated/ordered ahead of authentication; test `OPTIONS` with Spring Security active.

**12. Does a CORS error in DevTools always mean the server never received the request?**  
No. A failed preflight usually prevents the actual request from being sent; however, a simple or actual response missing headers can occur after the backend has already processed the request.

**13. Does `Origin: null` mean the request has no Origin?**  
No. It can come from an opaque origin; do not allow it automatically.

**14. Can `mode:"no-cors"` be used to read a JSON API?**  
Generally no. The response will be opaque, so JavaScript cannot read its body or status like a normal CORS response.

**15. Are SameSite cookies the same as a CORS allowlist?**  
No. SameSite governs sending cookies by site, whereas CORS governs JavaScript's permission to read responses by origin.

**16. Does reading a response with curl using a spoofed Origin prove CORS is misconfigured?**  
No. Curl does not enforce browser SOP; inspect backend headers and browser behavior instead.

**17. Why does OPTIONS preflight succeed in the demo while POST `/api/changes` can return 403?**  
Because CORS only permits the cross-origin method and headers; Spring Security CSRF still protects a POST lacking a token.

**18. If `Access-Control-Allow-Origin` is right yet the frontend still does not send cookies, what should you check?**  
`fetch.credentials`, cookie `SameSite`/`Secure`/`Domain`/`Path`, third-party cookie policies, and HTTPS; then check server authentication/session handling.

**19. Why must WebFlux configurations import `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`?**  
Because `ServerHttpSecurity.CorsSpec` expects a reactive CORS source; the Servlet class shares a similar name but has a different type.

**20. Can a public API use `Access-Control-Allow-Origin: *`?**  
Yes, when the data is genuinely public, does not rely on credentials, and has appropriate rate limiting; do not apply it by default to private data.

**Remember:** SOP protects cross-origin data access in the browser. CORS is the server's scoped consent allowing the browser to let JavaScript from specific origins **read responses**, governed by origin, method, headers, and credential mode. With Spring Security WebFlux, configure `CorsConfigurationSource` properly and process **preflight before authentication**, while keeping authentication, authorization, and CSRF as separate layers. Use browser tests alongside `WebTestClient` to verify both allowed and denied scenarios.

## References

- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): origin concept, same-origin access, exceptions, and opaque origins.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): CORS headers, preflight, credentialed requests, and browser errors.
- [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): fetch, credentials mode, response handling, and CORS errors.
- [WHATWG — Fetch Standard](https://fetch.spec.whatwg.org/): CORS protocol terminology, preflight, and credentials.
- [Spring Security — CORS for WebFlux](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS before security, `CorsWebFilter`, and `CorsConfigurationSource`.
- [Spring Security 6.3 — ServerHttpSecurity.CorsSpec](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html): `configurationSource(...)` in the reactive DSL and integration order.
- [Spring Framework — CORS in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `@CrossOrigin`, `HandlerMapping`, `CorsWebFilter`, credentials, and global policy.
- [Spring Framework — CorsConfiguration API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): `allowedOrigins`, `allowedOriginPatterns`, `allowedHeaders`, `maxAge`, and `allowCredentials`.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`, HTTP Basic, and `authorizeExchange`.
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): the difference between CSRF and CORS in cookie-based applications.
