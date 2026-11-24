# Distinguishing Browser CORS Errors from Server 401 or 403 Responses

> **Topic:** Spring Security – reactive  
> **Knowledge group:** CORS Configuration  
> **Focus:** Distinguishing three very different situations: **the browser blocking response reads due to CORS**, **the server returning 401 due to missing authentication**, and **the server returning 403 due to insufficient permissions, CSRF, or the CORS filter itself rejecting the request**. Self-diagnose using DevTools, `fetch()`, `curl`, and Java 17+ Spring Security WebFlux tests.

## 1. The Core Question: Why Does Console Report CORS Even When Network Shows 401?

Suppose the frontend runs at `http://localhost:5173` and calls a Spring WebFlux API at `http://localhost:8080/api/profile`:

```javascript
const response = await fetch("http://localhost:8080/api/profile", {
  credentials: "include"
});
console.log(response.status);
```

If the server returns `HTTP/1.1 401 Unauthorized` **without matching CORS headers**, the browser may **withhold the response from JavaScript**. Instead of executing `console.log(401)`, the `fetch` promise rejects with `TypeError: Failed to fetch` or a similar error; Console prints a CORS error. The **Network** tab may still display the HTTP status returned by the server. Both symptoms occur **on the exact same request**.

Conversely, if the server returns:

```http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
WWW-Authenticate: Basic realm="example"
```

and all other CORS conditions pass, JavaScript **receives a `Response` object with `status === 401`**. In that case, this is an **HTTP authentication error**, not a browser CORS error. By default, `fetch()` **does not reject** on 401 or 403 server responses; it resolves a `Response` with `ok === false`. Only network errors, CORS blocks, TLS errors, and fetch-layer failures reject the promise.

**Three conclusions to memorize:**

1. **CORS is a browser response-access policy**, not a check of username, password, or roles in Spring Security.
2. **401/403 are HTTP statuses returned by the server or an intermediary**; whether JavaScript can read that status still depends on CORS.
3. **A 401/403 response missing CORS headers can be "masked" by the browser as a CORS error**. Fixing Authentication/Authorization differs from fixing CORS; sometimes **both** must be fixed.

### Learning Objectives

You will be able to:

- Distinguish a `fetch` rejection caused by CORS/network from a `fetch` resolution with status 401/403.
- Correctly identify `OPTIONS` preflight, actual request, `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
- Distinguish CORS configuration failure, authentication failure, authorization failure, and CSRF failure.
- Configure `ServerHttpSecurity.cors(...)` with a proper `CorsConfigurationSource` for **Spring WebFlux reactive**.
- Test CORS on both successful responses **and 401/403 error responses**, not only 200 GETs.
- Use DevTools/Console/Network and `curl -i` to trace the request flow.
- Understand CORS limits: `curl` does not enforce CORS policies, CORS does not replace CSRF, and CORS does not protect APIs from non-browser clients.

## 2. What Is an Origin? Why Does Differing Only by Port Trigger CORS?

An **origin** consists of three parts: **scheme + host + port**. Two URLs share the same origin only when all three match.

| Frontend origin | API origin | Same origin? | Why? |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:5173` | Yes | Same scheme, host, and port |
| `http://localhost:5173` | `http://localhost:8080` | **No** | Different port |
| `https://app.example.test` | `https://api.example.test` | **No** | Different host |
| `https://example.test` | `http://example.test` | **No** | Different scheme |
| `http://127.0.0.1:5173` | `http://localhost:5173` | **No** | Different host |
| `https://app.example.test` | `https://app.example.test:443` | Yes | Default HTTPS port is 443 |

CORS typically affects cross-origin requests initiated by browser scripts such as `fetch` or `XMLHttpRequest`. CORS does **not** apply the same way to `curl`, Java HTTP clients, or backend-to-backend service calls. Same-site/cross-site (pertaining to `SameSite` cookies) is a **different** concept from same-origin/cross-origin; two different `localhost` ports are cross-origin even when considered same-site by some cookie mechanisms.

### 2.1. The Origin Request Header

For a cross-origin browser request:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
```

The browser reports the calling page's origin. The server checks whether this origin is on the trusted list and decides whether to emit CORS response headers. An `Origin` header **is not proof of authentication**: non-browser HTTP clients like curl can supply any `Origin`, so never treat `Origin` as a username, secret, or substitute for API authentication.

### 2.2. Do Not Confuse Access-Control-Allow-Origin with the Target URL

```http
Access-Control-Allow-Origin: http://localhost:5173
```

This is a **response header** returned by the server indicating which client origin is permitted to read the response. It is **not** the target API URL `http://localhost:8080`. If the server returns `Access-Control-Allow-Origin: http://localhost:3000` while the page runs on `:5173`, the browser still blocks it due to an origin mismatch.

When sending cross-origin credentials, `Access-Control-Allow-Origin: *` cannot be used for credentialed requests. The server must return an **explicit origin** plus `Access-Control-Allow-Credentials: true`, and the browser must be configured to send credentials appropriately.

## 3. Accurately Classifying Outcomes

A frontend request can result in **at least five distinct outcomes**:

| Scenario | What the browser sees | What JavaScript sees | Diagnosis |
| --- | --- | --- | --- |
| Server returns **200** and valid CORS | Network 200 | `Response(status=200, ok=true)` | Success |
| Server returns **401** and valid CORS | Network 401 | `Response(status=401, ok=false)` | Missing/invalid authentication |
| Server returns **403** and valid CORS | Network 403 | `Response(status=403, ok=false)` | Missing permission/CSRF/server policy |
| Server returns **401/403/200** with wrong/missing CORS headers | Network may show status | `fetch` **rejects**; script cannot read status/body | Browser blocked via CORS, though server **may still** have emitted an actual status |
| DNS/TLS/mixed content/timeout prevents a valid HTTP response | Network failed / canceled | `fetch` **rejects** | Network/protocol error; do not jump to CORS config conclusions |

There is also **preflight failure**: the browser sends `OPTIONS` first, sees a response rejecting the origin/method/header or returning 401/403/redirect, and **never sends the actual request**. In that case the `GET/POST` API controller may **never have run at all**.

**Decisive point:** HTTP 401/403 are protocol-level statuses; CORS failure is the browser's decision on whether JavaScript may consume the response. These two axes are **not mutually exclusive**.

### 3.1. fetch: Status 401/403 Is Not a JavaScript Exception

```javascript
async function callApi(url) {
  try {
    const response = await fetch(url, {
      mode: "cors",
      credentials: "include"
    });

    // Having a Response means the request passed CORS and the network layer
    // enough for the browser to let JS read the response.
    console.log("HTTP status =", response.status);
    console.log("HTTP ok =", response.ok);

    if (response.status === 401) {
      console.log("Login required or credentials are invalid/expired");
      return;
    }
    if (response.status === 403) {
      console.log("Denied by permissions, CSRF, or server policy");
      return;
    }
    if (!response.ok) {
      console.log("Other HTTP error:", response.status);
      return;
    }

    console.log("Body:", await response.text());
  } catch (error) {
    // No Response to read: catching does not automatically mean HTTP 401.
    console.error("Network / TLS / CORS / browser policy error:", error);
  }
}
```

Invoke `callApi` from a page opened at a real frontend origin, not `file://` where the origin becomes `null`. `fetch` can reject for many reasons: CORS, network, DNS, TLS, CSP `connect-src`, mixed content, extensions, aborted requests... Console + Network together tell them apart.

**Do not write:**

```javascript
try {
  await fetch(url);
} catch (error) {
  if (error.status === 401) {
    // Wrong: 401 normally arrives on Response, not inside catch.
  }
}
```

A `TypeError: Failed to fetch` does not prove the server returned 401, and this exception exposes no standard `status` property to inspect a CORS-blocked response's status.

### 3.2. no-cors Is Not a Fix

```javascript
fetch("http://localhost:8080/api/profile", {
  mode: "no-cors"
});
```

`no-cors` **does not grant permission to bypass CORS and read data**. On such cross-origin fetches, the browser returns an **opaque response**: `status === 0`, `type === "opaque"`, and headers/body remain unreadable. It also restricts allowed methods and request headers. Seeing the CORS message disappear does not mean your app works. Never use `no-cors` to mask errors in apps that need JSON or 401/403 handling.

## 4. Distinguishing OPTIONS Preflight from Actual Requests

Browsers perform a **CORS preflight** for many non-simple/non-safelisted requests, such as requests with a script-set `Authorization` header, `Content-Type: application/json`, custom `X-CSRF-TOKEN`, or methods like PUT/DELETE.

A typical preflight:

```http
OPTIONS /api/admin HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Allowed response:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
```

Listed methods/headers in the response may differ in casing or order; this example is illustrative. Only after validating it does the browser **send the actual GET**:

```http
GET /api/admin HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Authorization: Basic <base64-of-demo-user-password>
```

The actual request can return **200**, **401**, or **403** depending on authentication/authorization; a 200 preflight **does not mean** the user is authorized to access `/api/admin`.

### 4.1. Preflight Intentionally Contains No Credentials

A CORS `OPTIONS` preflight **carries no cookies or HTTP auth credentials** like an actual request. That is why Spring Security documentation requires **CORS to be processed before Spring Security authentication**; otherwise preflight fails with 401 as "unauthenticated" and the browser aborts the actual request. `<PRIVATE>` or `permitAll(OPTIONS)` alone does not guarantee the response carries required CORS headers.

In WebFlux, configure `ServerHttpSecurity.cors(...)` with a `CorsConfigurationSource` so Spring Security places the CORS `WebFilter` in the proper order. If preflight is blocked at a CDN, API gateway, proxy, or load balancer **before** reaching WebFlux, adjusting Spring Security alone is insufficient; fix the layer emitting the response.

### 4.2. When Is There No Preflight?

A simple cross-origin GET without custom/special headers can **skip preflight**; the browser sends the actual GET immediately. Even so, the actual response **must still carry valid CORS headers** for JavaScript to read it. Thus "no OPTIONS seen" **is not** proof that a request is same-origin or that CORS is configured properly.

A safelisted `application/x-www-form-urlencoded` POST can also be sent directly. CORS does not guarantee dangerous requests never reach the server here; when using browser cookies/sessions, **CSRF protection** must still be evaluated independently.

### 4.3. Preflight Caching

Browsers can cache preflight results per `Access-Control-Max-Age` and internal limits. Sometimes testing in an existing tab stops showing `OPTIONS` even for cross-origin calls because preflight was cached. While investigating, test in a fresh context/browser profile, mind the cache, and use `curl -i -X OPTIONS` to simulate preflight independently. Never assume a filter skipped preflight just because Network omitted `OPTIONS` on the second request.

## 5. Reading CORS Headers in the Right Direction

| Header | Direction | Role |
| --- | --- | --- |
| `Origin` | Request | Origin of the web page calling the API |
| `Access-Control-Request-Method` | Preflight request | Which method the browser intends for the actual request |
| `Access-Control-Request-Headers` | Preflight request | Which non-safelisted headers the browser intends to send |
| `Access-Control-Allow-Origin` | Response | Origin allowed to read the response |
| `Access-Control-Allow-Methods` | Preflight response | Permitted HTTP methods |
| `Access-Control-Allow-Headers` | Preflight response | Permitted request headers |
| `Access-Control-Allow-Credentials` | Response | Permits credentialed CORS requests when `true` |
| `Access-Control-Max-Age` | Preflight response | Suggested preflight cache duration |
| `Access-Control-Expose-Headers` | Actual response | Lets JavaScript read specified non-safelisted response headers |
| `Vary: Origin` | Response/cache | Keeps caches from mixing responses across different origins |
| `WWW-Authenticate` | HTTP 401 response | Authentication challenge, **not a CORS header** |

**Do not confuse `Access-Control-Allow-Headers: Authorization` with `Access-Control-Expose-Headers: Authorization`.** The first says the browser may **send request header** `Authorization`; the second lets the browser read a named **response header** if the server returns one. `Access-Control-Expose-Headers` neither grants permissions nor validates Basic/JWT credentials.

### 5.1. Credentials and Wildcards

When the frontend calls:

```javascript
fetch("http://localhost:8080/api/profile", {
  credentials: "include"
});
```

the server needs a valid response for credentialed requests, typically:

```http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
```

**Never return `Access-Control-Allow-Origin: *` with credentials `include`.** Spring Framework also rejects combining `allowedOrigins("*")` with `allowCredentials(true)`; if dynamic origins are needed, `allowedOriginPatterns` exists, yet patterns must be tightly constrained—never use `*` unconditionally for personal data.

`credentials: "include"` does not make the browser bypass `SameSite`, `Secure`, third-party cookie restrictions, or CSRF; whether cookies are actually sent still depends on cookie/browser policies. Even when CORS permits credentials, the server can still return 401 due to **missing/invalid cookies**.

### 5.2. Headers on Error Responses Matter Too

If the frontend needs to read 401/403 statuses, those error responses must also carry valid CORS headers. Do not attach CORS headers only inside 200 controllers while ignoring `AuthenticationEntryPoint`, `AccessDeniedHandler`, error responses, or reverse proxy 502s. A CORS `WebFilter` running early enough sets headers ahead of authorization in the Spring chain. However, if a gateway returns an error before the filter runs, the gateway must emit headers matching the policy without opening wildcard credentials.

## 6. Diagnostic Matrix: Browser, Server, and Root Cause

| Observation | Likely error source | What to check |
| --- | --- | --- |
| Console reports missing `Access-Control-Allow-Origin`; Network actual GET = 401 | Authentication failed **and** 401 lacks valid CORS headers | CORS config on error responses, then credentials |
| Network `OPTIONS` = 401; actual GET/POST never appears | Auth layer intercepted preflight | Order CORS before Spring Security; inspect gateway |
| Network `OPTIONS` = 403; no actual request | Origin/method/headers disallowed by CORS, or proxy/WAF blocked | Check CORS preflight request/response and 403 source |
| Network `OPTIONS` = 200 yet missing ACAO/ACAH/ACAM | CORS preflight rejected by browser | Fix CORS headers, method/header/origin |
| Network actual = 401; `fetch` gets `Response.status=401` | HTTP authentication | Are Basic/JWT/session valid? `WWW-Authenticate` present? |
| Network actual = 403; `fetch` gets `Response.status=403` | HTTP authorization/CSRF/another server policy | Role, scope, CSRF token, handler, matcher |
| Network actual = 403; JavaScript only catches `TypeError` | Invalid CORS response **despite HTTP 403** | Fix CORS on error responses before debugging 403 |
| No HTTP response and catches `TypeError` | DNS/TLS/mixed-content/CSP/connectivity | Network/Security/Console tabs, certificates, CSP |
| curl GET returns 200 yet browser blocks via CORS | curl does not enforce CORS policy | Use curl with `Origin` to **inspect headers**; verify in browser |
| API returns 403 for disallowed cross-origin | `CorsWebFilter` may actively reject | Compare requests with valid vs. invalid `Origin` |
| Same-origin works; cross-origin fails | CORS/credentials/cookie policy | Exact origin, ACAO/ACAC, preflight, `SameSite` |
| Network request returns redirect to login | Browser fetch followed redirect to another page/host | Check final URL, redirects, and CORS at every hop |

A CORS failure hides response details from JavaScript by design under the same-origin policy. DevTools lets developers inspect network traffic, yet app code must never guess 401/403 from a `TypeError`.

## 7. Step-by-Step Debugging Workflow in Chrome/Firefox DevTools

### 7.1. Reproducing in a Real Environment

1. Open the frontend page itself at origin `http://localhost:5173` (not `file://`).
2. Open DevTools → **Network**, enable Preserve log if redirects occur, and filter by endpoint URL or `Fetch/XHR`.
3. Open Console, call `fetch` with `try/catch`, and log `response.status` as in section 3.
4. Look for an **`OPTIONS`** request if present; record `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
5. Inspect **`OPTIONS` response headers**: do ACAO, ACAM, ACAH, and ACAC accept all requested values?
6. If `OPTIONS` passes, locate the **actual request**. Verify whether `Authorization`/cookies were sent, check for 401/403/200, and inspect CORS response headers.
7. If there is no `OPTIONS`, confirm whether the request is simple/safelisted or preflight-cached; still check CORS headers on the actual response.
8. If Network shows no clear HTTP response, inspect certificates, mixed content, browser extensions, CSP `connect-src`, DNS, and reverse proxies.
9. Compare with `curl` **with and without `Origin`** to separate HTTP authentication from CORS behavior.
10. Write integration tests for both preflights and error responses instead of applying temporary fixes to one endpoint.

### 7.2. What Happens When Console Reports "blocked by CORS policy"?

Console may state "No 'Access-Control-Allow-Origin' header…" or "Response to preflight request doesn't pass access control check…". That message explains **why the browser withheld the response from JS**. Do not misread it as "the API server is down" or "Spring Security always returns 403".

Browsers may also show `net::ERR_FAILED` or `TypeError` for non-CORS failures like TLS, certificates, or connection refused. When DevTools reports network/protocol errors, resolve infrastructure issues before tweaking CORS allowlists.

### 7.3. Distinguishing Backend URL from Frontend Origin

If the frontend origin is `http://localhost:5173`, the CORS allowlist needs `http://localhost:5173`, **not** `http://localhost:8080`. The backend URL is the request target; the allowed origin is the page **calling** the API.

Never try to set `Access-Control-Allow-Origin` as a request header from frontend JavaScript: that header must be **returned by the server**. Passing a self-invented `Access-Control-Allow-Origin` request header in `fetch` only complicates the request, triggers preflight, and solves nothing.

## 8. Proper Configuration in Spring Security WebFlux

Spring Security **reactive** uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `org.springframework.web.cors.reactive.CorsConfigurationSource`. **Never** copy Servlet `HttpSecurity`, `SecurityFilterChain`, or `CorsFilter` into Spring WebFlux.

In Spring Security 6.x, a typical pattern is:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http,
        UrlBasedCorsConfigurationSource corsSource) {
    return http
        .cors(cors -> cors.configurationSource(corsSource))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .pathMatchers("/api/admin").hasRole("ADMIN")
            .pathMatchers("/api/profile").authenticated()
            .anyExchange().denyAll())
        .httpBasic(withDefaults())
        .build();
}
```

**This is a snippet**; the complete project in section 10 includes imports, the authentication manager, and the user repository. `cors -> cors.configurationSource(corsSource)` is the official `ServerHttpSecurity.CorsSpec` API, placed in the proper order by Spring Security. CORS preflight is processed **before** authentication and needs no username/password.

WebFlux supports three common CORS approaches: a standalone `CorsWebFilter`, `WebFluxConfigurer.addCorsMappings` at `HandlerMapping`, or security-integrated `ServerHttpSecurity.cors(...)`. Never register **multiple overlapping CORS filters/policies** without understanding ordering; that causes duplicate headers, preflights handled in unexpected layers, or hard-to-debug behavior. This lesson chooses **a single `UrlBasedCorsConfigurationSource` wired directly into Spring Security**.

### 8.1. CorsConfigurationSource and the Allowlist

```java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("http://localhost:5173"));
config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
config.setAllowedHeaders(List.of(
    "Authorization", "Content-Type", "X-CSRF-TOKEN"));
config.setAllowCredentials(true);
config.setMaxAge(3600L);

UrlBasedCorsConfigurationSource source =
    new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/**", config);
```

- `allowedOrigins` specifies the **frontend** origin with exact scheme/host/port.
- `allowedMethods` lists methods permitted by CORS, **not** the inventory of implemented Spring controllers.
- `allowedHeaders` lets the browser send `Authorization`, `Content-Type`, and `X-CSRF-TOKEN` when preflight checks them. It does not grant login rights.
- `allowCredentials(true)` applies only when the frontend genuinely needs credentialed cross-origin requests. Never pair it with wildcard `allowedOrigins("*")`.
- `maxAge` governs preflight caching, not session/cookie/token TTL.
- `registerCorsConfiguration("/api/**", ...)` scopes CORS to API paths; `/actuator`, `/admin-console`, and `/internal` are not opened cross-origin automatically.
- `Vary` headers and actual ACAO responses are emitted by the CORS processor; avoid hardcoding manual headers in each controller.

### 8.2. Why Isn't permitAll on OPTIONS Enough?

```java
// Insufficient on its own:
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

This rule only tells Spring's `AuthorizationWebFilter` not to require an identity for `OPTIONS`. The browser **still** needs valid `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials` when required. Returning 200 without CORS headers still fails preflight. Proper CORS integration also validates origin, method, and headers rather than opening all `OPTIONS` blindly.

### 8.3. CORS Does Not Replace Authentication, Authorization, or CSRF

```text
CORS allowlist decides which origin's JS may read the response.
Authentication decides who the caller is.
Authorization decides whether that principal may access the resource.
CSRF protection decides whether an unsafe browser request has a valid token.
```

Therefore:

- A 200 preflight **does not guarantee** the actual GET returns 200.
- CORS 200 does not replace Basic credentials, sessions, or JWTs.
- CORS can let the frontend read **401/403** without exposing protected data.
- POSTs using cookies/sessions or browser Basic auth may require CSRF; a 403 after a passing preflight can be a **CSRF 403**, not CORS.
- CORS is strictly a browser gate and never stops non-browser API clients from calling endpoints; the server must still authenticate and authorize.

## 9. Plain Java 17: Modeling Fetch Outcomes Without Confusing Errors

Before Spring Security, a plain Java 17 example models classification using **observable outcomes** (no network calls, no replacement for a browser). The goal is separating server status from browser visibility.

File `CorsVsHttpModel.java`:

```java
public final class CorsVsHttpModel {

    static String describe(boolean readable, int serverStatus) {
        if (!readable) {
            return "browser blocked response; JS status unavailable";
        }
        if (serverStatus == 401) {
            return "HTTP 401: authentication problem";
        }
        if (serverStatus == 403) {
            return "HTTP 403: denied by server policy";
        }
        if (serverStatus >= 200 && serverStatus < 300) {
            return "HTTP success";
        }
        return "other readable HTTP response";
    }

    public static void main(String[] args) {
        System.out.println(describe(true, 200));
        System.out.println(describe(true, 401));
        System.out.println(describe(true, 403));
        System.out.println(describe(false, 401));
    }
}
```

Run:

```bash
javac CorsVsHttpModel.java
java CorsVsHttpModel
```

**Exact stdout:**

```text
HTTP success
HTTP 401: authentication problem
HTTP 403: denied by server policy
browser blocked response; JS status unavailable
```

The last line illustrates: **the server may have returned 401, yet JavaScript has no `Response.status` to read** when the browser blocks it via CORS. This is purely a model; real browsers enforce Fetch/CORS standards, whereas Java's standard HTTP clients have no CORS guard.

## 10. Runnable Project: WebFlux with CORS, 401, 403, and CSRF

The project uses **Spring Boot 3.5.16 + Java 17+ + Spring Security 6.x**. This is a specific release pinned for learning, **not a recommendation for new production deployments** in 2026 if that branch has reached end of OSS support; for new systems, pick a supported Spring Boot/Security branch and re-run tests per the migration guide.

### 10.1. Project Goals

- Allowed frontend origin: `http://localhost:5173`.
- Other origin `http://localhost:5174` is rejected by CORS.
- `GET /api/public`: public, 200.
- `GET /api/profile`: requires authentication; no credentials -> 401.
- `GET /api/admin`: requires `ROLE_ADMIN`; `reader` -> 403, `admin` -> 200.
- `POST /api/changes`: requires authentication **and a CSRF token** with default CSRF enabled; `OPTIONS` preflight still passes independently of authentication.
- Cross-origin responses from the allowed origin, including HTTP 401/403, carry **valid CORS headers** so the browser can read the status.
- `curl` without `Origin` still works under HTTP security policy; it is not subject to browser CORS checks.
- Includes **integration tests** using `WebTestClient` sending real `Origin`/`Access-Control-Request-*` headers; Java tests are not browsers, so inspect CORS headers as well as status codes.

File tree:

```text
reactive-cors-diagnostics/
├── pom.xml
└── src/
    ├── main/java/demo/cors/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/demo/cors/
        └── CorsAndHttpStatusTests.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-cors-diagnostics</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

`spring-boot-starter-webflux` brings in WebFlux/Reactor/Netty, `spring-boot-starter-security` integrates WebFlux Security, and `spring-security-test` provides the `csrf()` test helper. Do not add `spring-boot-starter-web` (Servlet MVC) to a reactive project. The validation starter is not required for CORS itself, though it illustrates API apps that validate inputs; omit it if you want a minimal build.

### 10.3. src/main/java/demo/cors/Application.java

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 10.4. src/main/java/demo/cors/SecurityConfiguration.java

```java
package demo.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Accounts strictly for localhost/test. Never hardcode real secrets.
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo123"))
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo123"))
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {

        return http
            // CORS is processed at the right position in Spring Security.
            .cors(cors -> cors.configurationSource(corsConfigurationSource))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/profile", "/api/changes").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic ->
                basic.authenticationManager(authenticationManager))
            .formLogin(form -> form.disable())
            // CSRF stays enabled by default; never disable it just because POST got 403.
            .build();
    }
}
```

**Explanation in order:**

1. `CorsConfigurationSource` defines the **frontend origin allowlist**, methods, request headers, and credentialed mode. `UrlBasedCorsConfigurationSource` comes from **`org.springframework.web.cors.reactive`**, not the Servlet class.
2. `.cors(cors -> cors.configurationSource(corsConfigurationSource))` uses `ServerHttpSecurity`'s CORS integration, running preflight ahead of authentication per WebFlux filter order.
3. `hasRole("ADMIN")` requires `ROLE_ADMIN`; a properly logged-in `reader` still gets 403 on `/api/admin`.
4. `httpBasic` produces clear 401 authentication challenges testable with `setBasicAuth`.
5. CSRF is **not disabled**. Because `/api/changes` is a POST, valid Basic auth without a CSRF token receives 403. That is a 403 cause **unrelated** to CORS or roles.
6. `cors.setAllowCredentials(true)` aligns with a frontend using `fetch(..., {credentials:"include"})`, without creating cookies or users; it merely lets browsers expose credentialed responses to the approved origin.
7. Do not add `@CrossOrigin("*")` on the controller, avoiding two conflicting configurations.
8. Policy scopes CORS to `/api/**`. If your app exposes auth/login/logout/CSRF endpoints outside that path, design allowlists for those paths per real requirements.

**Practical note:** if an app uses cross-site session cookies across two different sites, configure `SameSite=None; Secure` when appropriate, HTTPS, and CSRF protection; valid CORS **never forces the browser to send cookies blocked by its own policy**.

### 10.5. src/main/java/demo/cors/ApiController.java

```java
package demo.cors;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record ChangeRequest(String value) {}

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("profile OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }

    @PostMapping(value = "/api/changes",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<String> changes(@RequestBody Mono<ChangeRequest> body) {
        return body.map(request -> "changed:" + request.value());
    }
}
```

`POST /api/changes` does not generate or check CSRF tokens in the controller; Spring Security's `CsrfWebFilter` checks earlier. This isolates the case: **CORS preflight succeeds yet POST still returns 403 due to missing CSRF**, proving CORS success is not authorization success.

## 11. Integration Tests: The Same Origin Can Still Yield 200, 401, or 403

Because Java HTTP clients **are not browsers** and do not block responses based on CORS, `WebTestClient` tests must assert both **status and CORS response headers**. Asserting only `status=401` cannot prove a browser will be allowed to read that 401.

### 11.1. src/test/java/demo/cors/CorsAndHttpStatusTests.java

```java
package demo.cors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CorsAndHttpStatusTests {

    private static final String ALLOWED = "http://localhost:5173";
    private static final String DENIED = "http://localhost:5174";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec getWithOrigin(
            String uri, String username) {
        return client.get().uri(uri)
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(headers -> {
                if (username != null) {
                    headers.setBasicAuth(username, "demo123");
                }
            })
            .exchange();
    }

    @Test
    void allowedGetPreflightDoesNotRequireAuthentication() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void allowedPostPreflightHasNoPasswordOrSession() {
        client.options().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    }

    @Test
    void rejectedOriginPreflightGetsCors403NotAuth401() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, DENIED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void preflightWithUnsupportedMethodIsRejected() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightWithUnsupportedRequestHeaderIsRejected() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "x-evil-header")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void publicGetWithAllowedOriginHasReadable200() {
        getWithOrigin("/api/public", null)
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void missingAuthenticationHasReadable401() {
        getWithOrigin("/api/profile", null)
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void wrongBasicPasswordHasReadable401() {
        client.get().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }

    @Test
    void correctReaderHasReadable200() {
        getWithOrigin("/api/profile", "reader")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("profile OK");
    }

    @Test
    void authenticatedReaderLackingRoleHasReadable403() {
        getWithOrigin("/api/admin", "reader")
            .expectStatus().isForbidden()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }

    @Test
    void authorizedAdminHasReadable200() {
        getWithOrigin("/api/admin", "admin")
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void disallowedOriginActualGetIsRejectedByCors() {
        client.get().uri("/api/public")
            .header(HttpHeaders.ORIGIN, DENIED)
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void requestWithoutOriginIsNotSubjectToCorsHeaders() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void postWithoutCsrfIs403EvenThoughCorsAllowsOrigin() {
        client.post().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }

    @Test
    void postWithValidTestCsrfAndAuthenticationIs200() {
        client.mutateWith(csrf())
            .post().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED)
            .expectBody(String.class).isEqualTo("changed:hello");
    }

    @Test
    void postWithValidTestCsrfButNoAuthenticationIs401() {
        client.mutateWith(csrf())
            .post().uri("/api/changes")
            .header(HttpHeaders.ORIGIN, ALLOWED)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED);
    }
}
```

The test class contains **16 `@Test` methods**:

- The first five verify **preflight**: no credentials, allowed origin/method/headers, or CORS 403 when rejected.
- The next group proves **actual 200, 401, or 403 responses all include a valid ACAO** when the frontend origin is allowed.
- Requests with a rejected origin receive **HTTP 403 from the CORS processor**, distinct from a 403 from `hasRole`.
- Requests without an `Origin` operate under HTTP policy without needing ACAO.
- A POST without CSRF returns **403 even when CORS is valid**.
- `mutateWith(csrf())` is a test helper supplying matching tokens/attributes to **isolate the CSRF layer**. It is not the production frontend flow for fetching/storing tokens; real browsers need a server-issued CSRF token and valid cookies/session.

**CORS tests are not browser tests:** `WebTestClient` sees all server-emitted statuses and headers even when a browser would block them. Therefore, CORS tests must assert `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` when credentials apply, not just `expectStatus().isOk()`.

### 11.2. Quick Self-Check Test Matrix

| Request | Expected HTTP | CORS headers | What it proves |
| --- | --- | --- | --- |
| OPTIONS /api/profile, allowed origin, asks for Authorization | **200** | ACAO=allowed | Preflight needs no auth |
| OPTIONS /api/changes, allowed origin, POST/JSON/auth | **200** | ACAO, ACAC=true | Browser may send actual request |
| OPTIONS disallowed origin | **403** | No ACAO | CORS processor blocks |
| OPTIONS requesting DELETE (not allowed) | **403** | Method rejected | Preflight fails |
| GET /api/public, allowed Origin | **200** | ACAO | Publicly readable |
| GET /api/profile, no Basic, allowed Origin | **401** | ACAO | HTTP auth error is readable |
| GET /api/profile, wrong Basic, allowed Origin | **401** | ACAO | Password/auth error is readable |
| GET /api/admin, reader Basic, allowed Origin | **403** | ACAO | HTTP authz error is readable |
| GET /api/admin, admin Basic, allowed Origin | **200** | ACAO | Authn + authz succeed |
| GET /api/public, denied Origin | **403** | No ACAO | CORS failure |
| GET /api/public, no Origin | **200** | No ACAO needed | No browser CORS check |
| POST /api/changes, valid Basic, missing CSRF | **403** | ACAO | CSRF failure does not equal CORS |
| POST /api/changes, valid Basic, valid test CSRF | **200** | ACAO | Passed CSRF + authentication |
| POST /api/changes, valid test CSRF, missing Basic | **401** | ACAO | CSRF does not replace authentication |

If 401/403 responses lack ACAO in a live environment despite passing Spring-context tests, check **reverse proxies, gateways, error page handlers, other security chains, or out-of-context HTTP servers**. Include an end-to-end test layer through the gateway when infrastructure has multiple error-producing hops.

## 12. Hands-On with curl: See Real HTTP Without Pretending to Be a Browser

### 12.1. Running the Project

Requires Java 17+ and a compatible Maven. Place files in package `demo.cors` and run:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

The code includes **16 tests**; Surefire is expected to report `Tests run: 16, Failures: 0, Errors: 0` with `BUILD SUCCESS` in a compatible environment. This is an **expectation derived from the code**, not a claim it was executed on the reader's machine.

### 12.2. Simulating Allowed-Origin Preflight

```bash
curl -i -X OPTIONS http://localhost:8080/api/profile \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Expected HTTP **200** with `Access-Control-Allow-Origin: http://localhost:5173`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials: true`. No `-u` is needed on preflight because browser preflight **carries no credentials**.

### 12.3. Simulating Denied-Origin Preflight

```bash
curl -i -X OPTIONS http://localhost:8080/api/profile \
  -H "Origin: http://localhost:5174" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Expected HTTP **403 Invalid CORS request**, with no ACAO for the rejected origin. **This is a 403 from the CORS processor**, not an authenticated user lacking a role; the request never even reached controller logic.

### 12.4. Actual 401 with Valid CORS

```bash
curl -i http://localhost:8080/api/profile \
  -H "Origin: http://localhost:5173"
```

Expected HTTP **401** with `WWW-Authenticate` and `Access-Control-Allow-Origin: http://localhost:5173`. If a browser sends GET without valid authentication (even though CORS passes), JavaScript sees status 401.

### 12.5. Actual 403 Due to Missing Role

```bash
curl -i -u reader:demo123 http://localhost:8080/api/admin \
  -H "Origin: http://localhost:5173"
```

Expected HTTP **403** and ACAO matching the frontend origin. User `reader` is logged in yet lacks `ROLE_ADMIN`. This is an **authorization** 403, not a CORS error.

### 12.6. Actual 200 with ADMIN Role

```bash
curl -i -u admin:demo123 http://localhost:8080/api/admin \
  -H "Origin: http://localhost:5173"
```

Expected HTTP **200** with body `admin OK` and ACAO. If frontend JS still cannot read the response, check actual browser headers, redirects/proxies, credentials mode, and exact origin.

### 12.7. No Origin Can Also Return 200 from curl

```bash
curl -i http://localhost:8080/api/public
```

Expected HTTP **200** with `public OK`, needing no ACAO. This illustrates: CORS **does not lock URLs away from non-browser clients**; it only governs browser cross-origin reading.

**Shell security:** `reader:demo123` and `admin:demo123` are public test fixtures; for real accounts, never put passwords into command history or logs. On PowerShell, use `curl.exe`; `\` line continuation is Bash syntax and must be adapted for PowerShell.

## 13. Browser Fetch Lab to Observe Both Failure Modes

Open a real frontend page at `http://localhost:5173` (e.g., a Vite dev server) and run this snippet in the DevTools Console; **do not run it from `file://`**, where the origin can become `null`.

```javascript
const api = "http://localhost:8080";

async function inspect(path, username, password) {
  const headers = {};
  if (username) {
    // Strictly US-ASCII demo credentials. Never put real passwords in JS.
    headers.Authorization = "Basic " + btoa(username + ":" + password);
  }

  try {
    const response = await fetch(api + path, {
      method: "GET",
      mode: "cors",
      credentials: "include",
      headers
    });

    console.log({
      path,
      status: response.status,
      ok: response.ok,
      type: response.type
    });

    if (response.status === 401) {
      console.log("This is a readable HTTP 401");
    } else if (response.status === 403) {
      console.log("This is a readable HTTP 403");
    } else {
      console.log("Body:", await response.text());
    }
  } catch (error) {
    console.error("Fetch rejected (network/CORS/etc):", error);
  }
}

await inspect("/api/public");
await inspect("/api/profile");
await inspect("/api/profile", "reader", "wrong");
await inspect("/api/profile", "reader", "demo123");
await inspect("/api/admin", "reader", "demo123");
await inspect("/api/admin", "admin", "demo123");
```

With the project's CORS policy, expected outcomes:

```text
GET /api/public                    -> Response.status 200
GET /api/profile, no credentials  -> Response.status 401
GET /api/profile, wrong password  -> Response.status 401
GET /api/profile, valid reader    -> Response.status 200
GET /api/admin, reader            -> Response.status 403
GET /api/admin, admin             -> Response.status 200
```

For requests carrying a script-set `Authorization` header, the browser sends an `OPTIONS` preflight first. Even when preflight returns 200, the actual GET can still return 401/403. Console commands also require the server to be running, the exact `:5173` frontend origin, and no proxy altering requests/headers.

**Trying a wrong origin:** if the frontend runs at `http://localhost:5174` while the backend allows only `:5173`, scripts receive a `TypeError`/CORS error instead of a status. For a simple GET, the backend CORS filter can return HTTP 403 on the actual GET; when sending `Authorization`, preflight itself usually gets 403 and the actual GET is never sent.

### 13.1. Never Hardcode Real Passwords in JavaScript

`btoa("reader:demo123")` is strictly a **localhost demo pattern**. Basic Base64 is **not secure encryption**; anyone can inspect source/DevTools. Production browser apps must use proper login/credential handling (sessions, OIDC/OAuth2...) and HTTPS—never embed shared secrets in frontend bundles.

## 14. When It Is Not CORS Yet Looks Like CORS

### 14.1. Authentication Redirecting to a Login Page

Apps with form login may return a `302` redirect to `/login` instead of 401. Browser `fetch` follows redirects by default; if the final page has another origin or lacks CORS headers, Console reports CORS. When debugging, enable **Preserve log** and check the redirect chain, final URL, request headers, and policy at **every hop**. Do not just add ACAO to the initial endpoint if the blocked response came from the redirect target.

### 14.2. Reverse Proxy/WAF Returning 401/403/502 Before Spring

An API gateway may demand an API key, a WAF may block an IP, or a load balancer may error when an upstream is down. In those cases, controllers and `SecurityWebFilterChain` **may never have run**. If the gateway error lacks ACAO, the browser reports CORS and developers mistakenly edit Spring.

Diagnose with request IDs, redacted access logs, upstream status codes, and response `Server`/proxy headers when safe, tracing the request through the infrastructure. Proxy CORS policies must align with the backend; never return `*` with credentials as a quick "fix".

### 14.3. TLS, Mixed Content, DNS, Firewalls, and CSP

An HTTPS page calling an HTTP API is blocked by **mixed content** before any HTTP response exists. Invalid certificates, DNS failures, connection refused, CSP `connect-src`, extensions, or ad blockers also trigger `Failed to fetch`. Do not tweak CORS config to fix certificates, unreachable reverse proxies, or CSP.

### 14.4. Cookies Not Sent with Requests

CORS headers are valid yet the server returns 401 because the session cookie was withheld. Inspect `credentials: "include"`, `SameSite`, `Secure`, cookie domain/path, browser privacy settings, and whether URLs mix `localhost` and `127.0.0.1`. **Simply setting `Access-Control-Allow-Credentials: true` does not create cookies** or override `SameSite`/third-party cookie policies.

### 14.5. CSRF Blocking POST After Preflight Passes

A POST carrying `Authorization`, `Content-Type: application/json`, or `X-CSRF-TOKEN` can pass preflight, then receive **403** from Spring Security's `CsrfWebFilter` due to a missing or expired CSRF token. When CORS headers are valid, JavaScript receives `Response.status=403`; fix the CSRF token/session flow—do **not** disable CORS and do **not** reflexively disable CSRF.

### 14.6. Browser Rejecting Wildcard ACAO with Credentials Include

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

This is **not** a valid configuration for browsers to expose credentialed responses. From a frontend using `credentials:"include"`, the browser withholds access from JavaScript even if the server returned 200. Fix with a trusted explicit origin and proper cookie/authn policies.

## 15. Testing Habits for Distributed Systems

In production deployments with CDNs, ingress, API gateways, Spring WebFlux, and identity providers, test every layer:

| Layer | What to test | Goal |
| --- | --- | --- |
| Unit/config | Allowed origins, methods, headers, credentials | No accidental wildcards or arbitrary origin exposure |
| WebFlux integration | `OPTIONS` and actual 200/401/403 responses | CORS integrated ahead of authentication |
| Authentication | Missing/wrong/valid credentials | Clear 401 independent of CORS |
| Authorization | Roles/scopes/tenants/objects | Clear 403 independent of CORS |
| CSRF | Unsafe methods with/without/expired CSRF | Never confuse CSRF 403 with role 403 |
| Browser E2E | `fetch` from real frontend origin, cookie behavior | JavaScript reads valid 401/403 statuses |
| Gateway E2E | Error responses from gateway/WAF and redirects | CORS headers not stripped in intermediary layers |
| Security | Wildcard + credentials, Origin reflection, XSS/CSRF | Sensitive API data never exposed to bad origins |
| Observability | Request IDs, CORS/preflight metrics, redaction | Debuggable without leaking tokens or passwords |

**Beware "reflect any Origin":** middleware that copies the incoming `Origin` straight into `Access-Control-Allow-Origin` regardless of value alongside `Allow-Credentials: true` allows malicious websites to read sensitive user data. A CORS allowlist is a **trust decision**, not merely a way to silence Console errors.

## 16. Common Programming Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `allowedOrigins("http://localhost:8080")` instead of frontend `:5173` | Browser blocked | Use the origin of the **calling page** |
| Adding `Access-Control-Allow-Origin` only in 200 controllers | JS cannot read 401/403 | Use a CORS filter/source ahead of security/errors |
| Requiring session cookie on `OPTIONS` | Preflight 401 | Let CORS processor run before auth |
| Only `permitAll(OPTIONS)` | Preflight 200 yet lacks CORS headers | Configure a real CORS source |
| Using Servlet `CorsFilter` in WebFlux | Wrong stack or order | Use reactive `CorsWebFilter`/`ServerHttpSecurity.cors` |
| `allowedOrigins("*")` + `allowCredentials(true)` | Invalid / rejected by browser | Specify trusted origins |
| Forgetting `Authorization` in allowed headers | Preflight rejected | Add exact required request headers |
| Setting `Access-Control-Expose-Headers` instead of `Allow-Headers` | Does not resolve preflight | Distinguish request vs. response headers |
| Catching `TypeError` and reading `error.status` | Cannot detect 401/403 | Inspect `response.status` when `fetch` resolves |
| Enabling `mode: "no-cors"` | Opaque response, status 0, unreadable body | Fix server CORS config |
| `curl` returns 200, assuming browser allows it | curl does not enforce CORS | Check response headers and test in browser |
| CORS passes, POST 403, disabling CSRF | Creates CSRF vulnerability | Send a valid CSRF token for the same session |
| CORS passes yet missing cookie, 401 | Wrong cookie policy/credentials mode | Check credentials, `SameSite`, `Secure`, domain |
| Treating `Origin` as user identity | Authentication bypass | Authenticate independently via session/JWT/Basic |
| Reflecting arbitrary `Origin` + credentials | Data leaked to bad origins | Enforce strict allowlist |
| Preflight missing from Network | Simple request or preflight cached | Inspect request headers/cache |
| Gateway 502 lacks ACAO | Browser reports CORS; app never ran | Fix gateway/upstream and error handling |
| Disabling CORS in Spring to "turn off CORS errors" | Browser still enforces same-origin policy | Enable proper CORS support |
| Two conflicting CORS configurations | Inconsistent headers, hard to debug | Pick one clear source/policy |

## 17. Self-Check Questions

**Q1.** Does `fetch()` reject when the server returns 401 with valid CORS headers?  
**Answer:** Under standard Fetch behavior, **no**. The promise resolves a `Response` with `response.status === 401` and `response.ok === false`.

**Q2.** The server returns 401 without ACAO—can JavaScript read status 401?  
**Answer:** On cross-origin requests requiring CORS, the browser blocks the response and rejects `fetch`; JavaScript cannot read status 401 even though DevTools Network may show HTTP 401.

**Q3.** Does a 200 `OPTIONS` preflight guarantee actual `GET /api/admin` returns 200?  
**Answer:** No. Preflight checks CORS permissions only, not user/role auth. The actual GET can still return 401 or 403.

**Q4.** Does the browser send credentials in an `OPTIONS` preflight?  
**Answer:** CORS preflight does not carry cookies or HTTP auth credentials like an actual request. Running CORS before authentication is essential.

**Q5.** User `reader` has the right password yet lacks `ROLE_ADMIN`—what does the server return?  
**Answer:** Typically **403 Forbidden**; with valid ACAO, JS sees status 403. This is authorization, not CORS.

**Q6.** What else can cause a 403 on an `OPTIONS` request?  
**Answer:** The CORS processor returns 403 when the origin, requested method, or requested headers are disallowed; a WAF/gateway can also return 403. Do not automatically blame roles.

**Q7.** What is the difference between `Access-Control-Allow-Headers` and `Access-Control-Expose-Headers`?  
**Answer:** `Allow-Headers` permits request headers the browser wants to **send**; `Expose-Headers` lets JS read extra response headers the server **returns**.

**Q8.** Why can't frontend origin `http://localhost:5173` be replaced by `http://localhost:8080` in ACAO?  
**Answer:** ACAO must permit the **calling page's origin**, whereas `:8080` is the API destination.

**Q9.** Is adding `mode:"no-cors"` a proper fix?  
**Answer:** No. Cross-origin responses become opaque, leaving JS unable to read body or status; it does not bypass CORS restrictions.

**Q10.** `curl` without `Origin` gets 200—can the browser frontend read 200 too?  
**Answer:** No. curl does not enforce CORS. Browsers require valid CORS headers on cross-origin calls.

**Q11.** A POST with valid Basic auth yet missing a CSRF token returns 403—does that mean CORS is broken?  
**Answer:** No. CSRF is a separate check; if CORS headers are present, JavaScript receives status 403 to handle.

**Q12.** Does `credentials:"include"` force cross-site cookies to always be sent?  
**Answer:** No. Cookies remain subject to `SameSite`, `Secure`, domain/path, and browser policies.

**Q13.** If a gateway returns 401 without ACAO before reaching Spring Security, is updating `CorsConfigurationSource` in the app enough?  
**Answer:** Not yet. You must fix the gateway/error-response path itself; Spring filters cannot add headers to responses emitted earlier by the gateway.

**Q14.** Is adding `permitAll(OPTIONS)` alone a complete CORS solution?  
**Answer:** No. The browser still needs ACAO, ACAM, ACAH, and ACAC when applicable, matching the actual origin/method/headers.

**Q15.** If Console reports CORS yet Network shows no HTTP response, should you immediately edit `allowedOrigins`?  
**Answer:** Don't jump straight to it. Check DNS, TLS, mixed content, CSP, timeouts, and extensions first; not every `Failed to fetch` is a CORS config issue.

## 18. Production Checklist

- [ ] Frontend and backend origins are identified accurately by scheme/host/port.
- [ ] CORS source allows only **trusted origins**, never reflecting arbitrary Origins.
- [ ] `allowedMethods`/`allowedHeaders` match actual preflight needs without needless widening.
- [ ] When credentials are included, ACAO is an explicit origin, ACAC=true, and cookie policies are valid.
- [ ] `OPTIONS` preflight is never blocked accidentally by authentication or gateways; CORS runs before auth.
- [ ] **401/403** responses from both Spring **and gateways** carry valid CORS headers when the frontend is permitted.
- [ ] CORS does not replace authentication, authorization, CSRF, or server-side permission checks.
- [ ] `mode:"no-cors"` is never used to silence errors.
- [ ] `fetch` handles `response.status` after resolution and uses `catch` separately for network/CORS errors.
- [ ] DevTools verified for `OPTIONS` + actual requests, responses, redirects, caching, and cookies.
- [ ] Integration tests cover preflight, actual 200, auth 401, role 403, CSRF 403, and denied origins.
- [ ] Real browser E2E tests run from the actual frontend origin, not only curl/`WebTestClient`.
- [ ] No real credentials in JavaScript source; HTTPS, secret management, and standard CSRF are enforced.
- [ ] `Authorization`/Cookie/CSRF tokens are never leaked into logs or traces.
- [ ] Runbooks exist for gateway/WAF/IdP errors and per-service/chain CORS policies.
- [ ] Proper `Vary: Origin` and caching behavior enforced whenever ACAO depends on `Origin`.

## 19. Summary and References

**Fastest rule of thumb:**

```text
fetch RESOLVES + response.status = 401
    -> HTTP Authentication failed; CORS let JS read the response.

fetch RESOLVES + response.status = 403
    -> HTTP server policy denied (role, CSRF, ...); CORS let JS read it.

fetch REJECTS + TypeError / CORS error
    -> JS has no Response. Inspect DevTools OPTIONS/actual/TLS/network.
       The server MAY STILL have emitted HTTP 200/401/403 blocked by CORS.

OPTIONS 200
    -> CORS preflight accepted; the actual request can still return 401/403.

curl 200
    -> Does NOT prove browser CORS passes.
```

In essence: **CORS is neither authentication nor authorization**. Always examine *two independent axes*: (1) whether the browser is permitted to read the HTTP response, and (2) whether the server accepts the credentials/role/CSRF and what status it returns. Never "fix" CORS by disabling Spring Security or opening all origins; never "fix" 401/403 by switching `fetch` to `no-cors`.

**Official references consulted:**

- Spring Security – Reactive CORS integration (handling preflight before authentication): https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security 6.5 – `ServerHttpSecurity.CorsSpec` (configurationSource): https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Security 6.5 – `ServerHttpSecurity` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Framework – WebFlux CORS (`HandlerMapping` and `CorsWebFilter`): https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- MDN – Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN – Using Fetch API, response vs network error: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch
- MDN – CORS Errors (console/network/preflight): https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors
- MDN – Credentials and ACAO wildcard: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials
- MDN – Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- OWASP – CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
