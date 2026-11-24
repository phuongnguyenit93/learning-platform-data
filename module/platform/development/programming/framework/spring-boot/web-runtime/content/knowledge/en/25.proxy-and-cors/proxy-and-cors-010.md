# `allowCredentials` and restrictions on wildcard origins

## 1. Goal and key takeaway

A frontend running at `https://app.example.com` calls an API at `https://api.example.com`. The two URLs have **different origins**, so the browser applies CORS (Cross-Origin Resource Sharing) to requests sent by JavaScript. If the API uses login/session cookies, the browser needs to know whether the response may be shared with the **specific calling origin** when the request carries credentials.

In Spring MVC and Spring WebFlux, `allowCredentials` is an important setting, yet it comes with a strict limitation:

> When enabling `allowCredentials(true)`, **do not use `allowedOrigins("*")`**. Specify a list of trusted origins or use tightly scoped `allowedOriginPatterns(...)`. For credentialed requests, the `Access-Control-Allow-Origin` header must never have the literal value `*`.

Valid example for an allowed frontend:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Invalid example for browsers when sending credentials:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

This is not merely a framework recommendation: browsers refuse to allow credentialed CORS responses to use the `*` wildcard in `Access-Control-Allow-Origin`. Since Spring Framework 5.3, Spring also **validates the configuration** and can throw `IllegalArgumentException` when `allowedOrigins` contains `*` together with `allowCredentials=true`.

After this lesson, you will be able to:

1. Determine an origin from **scheme + hostname + port**, and distinguish cross-origin from cross-site.
2. Explain the meaning of `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers`.
3. Compare Spring's `allowedOrigins` and `allowedOriginPatterns`, understanding why patterns work with credentials while overly broad wildcards remain dangerous.
4. Configure CORS for Spring MVC and WebFlux without mixing up annotations/configurers between the two stacks.
5. Run a Spring Boot 3.3.5 / Java 17 example with a frontend on a different port, session cookies, `fetch(credentials: "include")`, and preflight.
6. Understand how to integrate with Spring Security, CSRF, `SameSite`/`Secure` cookies, and reverse proxies.
7. Diagnose browser errors such as "Credential is not supported if the CORS header ... is `*`", 403 preflight, missing cookies, or duplicate CORS headers.

**Scope:** CORS in the web runtime. This lesson demonstrates session cookies to observe credentialed requests, without building a full user authentication system.

## 2. What is an origin? Why does it differ from a site?

An **origin** is defined by the triple **scheme (protocol), host (domain/IP), and port**. The following origins differ:

| Page or API | Compared to `https://app.example.com` | Reason |
| --- | --- | --- |
| `https://app.example.com` | Same origin | Same scheme, host, and default port 443 |
| `http://app.example.com` | Different origin | `http` scheme differs from `https` |
| `https://api.example.com` | Different origin | Different host |
| `https://app.example.com:8443` | Different origin | Different port |
| `https://app.example.com:443` | Same origin via standard port normalization | Same HTTPS and default port |
| `http://localhost:5173` vs. `http://localhost:8080` | Different origin | Port 5173 differs from 8080 |

**An origin does not include the path:** `https://api.example.com/v1` and `https://api.example.com/v2` belong to the same origin because only the path differs. Therefore `allowedOrigins("https://app.example.com/login")` is not how you declare an origin scoped by path.

**Cross-origin does not necessarily mean cross-site.** For example, `http://localhost:5173` and `http://localhost:8080` are cross-origin due to port, yet are usually treated by browsers as **same-site** under the current site model. By contrast, `https://shop.example.com` and `https://third-party.test` are cross-site. CORS controls JavaScript's response read access by **origin**; `SameSite` cookies evaluate **site** and scheme per cookie rules. These two controls are related but not identical.

Browsers normally add the `Origin` request header when JavaScript sends a cross-origin request:

~~~http
Origin: https://app.example.com
~~~

The server checks `Origin` against its CORS policy. Never use `Origin` as proof of user identity: non-browser HTTP clients can forge any header, and `Origin: null` can come from sandboxed iframes, `file:`, or opaque-origin contexts. Private APIs must enforce independent authentication and authorization.

## 3. What does CORS do and what does it NOT do?

The **Same-Origin Policy** protects web pages by restricting JavaScript on origin A from reading data from origin B unless B explicitly permits it. CORS is the HTTP mechanism letting **server B actively open response sharing** to origin A under predefined conditions.

CORS is not:

- An authentication filter: an allowed origin does not mean the caller is logged in.
- An authorization layer: user A must not read user B's orders even if both use a trusted origin.
- A firewall blocking all clients: `curl`, mobile apps, or backend-to-backend clients are not restricted by browser CORS enforcement.
- A complete CSRF defense: a "simple" request can reach the server and mutate state before the browser decides whether to let JS read the response.
- Proof that HTTPS or cookies work: those depend on TLS, cookie policies, and the HTTP client.

**CORS primarily governs response access from JavaScript in a browser.** It can prevent the browser from sending an actual request when preflight fails, yet it cannot guarantee blocking every dangerous request from reaching the server.

### 3.1. Three request types to distinguish

| Type | Mechanism | Example |
| --- | --- | --- |
| Same-origin | No CORS needed | JS from `https://app.example.com` calls an API on the same origin |
| Cross-origin "simple" | Browser sends actual request, then checks CORS response | `GET` with only CORS-safelisted headers |
| Cross-origin with preflight | Browser sends `OPTIONS` to ask permission first, then sends actual request if preflight passes | `POST` JSON with `Content-Type: application/json`, `DELETE`, custom headers |

The term "simple request" is practical shorthand in CORS docs; exact criteria rely on method/header/content-type safelists, not merely small payload size.

## 4. Headers governing credentialed CORS

### 4.1. Headers sent by the client

~~~http
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Here `Access-Control-Request-*` appears on **`OPTIONS` preflight**, describing the planned actual request.

### 4.2. Headers returned by the server

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Meaning:

- `Access-Control-Allow-Origin`: only **one explicit origin**, or wildcard `*` when credentials are not used under allowed cases; never a comma-separated list of multiple origins.
- `Access-Control-Allow-Credentials: true`: lets the browser expose the response of a credentialed CORS request when other conditions also pass. `true` is the valid value; when disallowing, typically **omit the header** rather than sending `false`.
- `Access-Control-Allow-Methods`: HTTP methods allowed on the actual request after preflight.
- `Access-Control-Allow-Headers`: allowed request headers, such as `Content-Type` or `X-CSRF-Token`.
- `Access-Control-Max-Age`: lets the browser cache the **preflight outcome** within browser-imposed caps; not an HTTP response cache for API data.
- `Vary`: informs shared caches that CORS responses may depend on `Origin` or preflight headers, preventing permission leaks across origins.

`Access-Control-Allow-Origin` must match the actual `Origin` (or a valid wildcard in non-credentialed cases). When permitting multiple trusted origins, the server **picks and echoes the single matching origin per request**, never emitting:

~~~http
Access-Control-Allow-Origin: https://app.example.com, https://admin.example.com
~~~

That line is not valid syntax for granting browser access to two origins.

### 4.3. `Access-Control-Expose-Headers` is separate

By default, browsers let JavaScript read only safelisted response headers. If the app wants JS to read a response header like `X-Request-Id`, configure the corresponding exposed header:

~~~http
Access-Control-Expose-Headers: X-Request-Id
~~~

Spring permits `*` in certain `allowedHeaders`, `allowedMethods`, and `exposedHeaders` settings even with credentials enabled; Spring's emitted header behavior has nuances (section 7). **Do not confuse wildcards on those fields with a wildcard on `allowedOrigins`:** the central rule of this lesson is that `Access-Control-Allow-Origin` must never be `*` when the browser uses credentials.

## 5. What does `allowCredentials` mean?

In Spring:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins("https://app.example.com")
        .allowCredentials(true);
~~~

`allowCredentials(true)` instructs Spring to permit requests carrying credentials under CORS by emitting `Access-Control-Allow-Credentials: true` when the origin matches.

Browser-managed credentials include **cookies**, **HTTP authentication credentials**, and **TLS client certificates** in their respective contexts. Whether a client manually sets an `Authorization` header also depends on request configuration, CORS preflight, and auth flows; not every bearer-token API needs `allowCredentials(true)`.

Common misconceptions:

- `allowCredentials(true)` **does not send cookies automatically**. Frontend `fetch` must use the matching mode (`credentials: "include"` for cross-origin), and cookies must have valid `Domain`/`Path`/`SameSite`/`Secure` and not be blocked by the browser.
- `allowCredentials(true)` **does not establish a session**, create a login, or generate a CSRF token.
- `allowCredentials(false)` or omitting it does not mean the server rejects all HTTP requests; CORS is a browser mechanism governing cross-origin data access.
- If cookies are sent to an API that replies `Access-Control-Allow-Origin: *`, the browser still **blocks JavaScript from reading the response**. Cookies may already have been sent on an actual simple request before the browser checked the CORS response.
- CORS authorizes an **origin**, not an individual user. Any page or JavaScript running on the trusted origin inherits that permission under the policy.

### 5.1. Role of the `fetch` credentials mode

~~~javascript
// Default: credentials: "same-origin"
// Does not automatically send cookies on cross-origin fetch.
fetch("https://api.example.com/me");

// Instructs the browser to send/accept cookies on cross-origin requests,
// within applicable cookie policies.
fetch("https://api.example.com/me", {
  credentials: "include"
});
~~~

With `XMLHttpRequest`, set `xhr.withCredentials = true` before `send()`. With `EventSource`, pass `withCredentials: true` for compatible cross-origin streams.

**`credentials: "include"` does not override browser policies.** Cookies may still be blocked by `SameSite`, `Secure`, `Domain`, `Path`, cross-site tracking protections, privacy settings, or third-party cookie blocking. Seeing `Access-Control-Allow-Credentials: true` does not guarantee the browser successfully sent the cookie.

### 5.2. Does preflight send cookies?

Per the standard specification and Spring Security docs, **CORS preflight `OPTIONS` does not carry `JSESSIONID` session cookies like the actual request**. The browser checks cross-origin permission before sending the credentialed actual request. Therefore, having an authentication filter block preflight (401/403/redirect to login) is a very common misconfiguration.

Flow:

~~~text
Frontend app.example.com
    |
    | OPTIONS /api/order
    | Origin: https://app.example.com
    | Access-Control-Request-Method: POST
    | Access-Control-Request-Headers: content-type,x-csrf-token
    v
API / CORS layer
    |
    | Allows only configured origin + method + headers
    | Access-Control-Allow-Origin: https://app.example.com
    | Access-Control-Allow-Credentials: true
    v
Browser accepts preflight?
    |
    +-- No  -> STOPS actual request, reports CORS error
    |
    '-- Yes -> POST actual request may carry session cookie
               (if fetch and cookie policy allow)
               |
               v
           AuthN/AuthZ/CSRF/Business logic
               |
               v
           Response still needs matching CORS headers
~~~

A passing preflight **does not prove** the actual request will return 200. The actual request can still return 401/403 due to authentication, authorization, or CSRF, and error responses still need proper CORS headers so the frontend can inspect error details appropriately.

## 6. Why do wildcard origins and credentials conflict?

### 6.1. Invalid configuration

~~~java
// Wrong when combined with credentialed CORS:
registry.addMapping("/api/**")
        .allowedOrigins("*")
        .allowCredentials(true);
~~~

Even if a framework emitted both headers:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

browsers would refuse to let JavaScript on a credentialed request read the response. MDN documents the error message:

~~~text
Reason: Credential is not supported if the CORS header
'Access-Control-Allow-Origin' is '*'
~~~

Spring Framework 5.3+ provides `CorsConfiguration.validateAllowCredentials()`. When `allowedOrigins` contains `*` and `allowCredentials=true` is validated/applied, Spring can throw `IllegalArgumentException` rather than emitting an invalid CORS combination. **When detection occurs** depends on the configuration path and when the handler/CORS processor runs; do not assume every project fails immediately at startup.

### 6.2. Right configuration for a few origins

~~~java
registry.addMapping("/api/**")
        .allowedOrigins(
                "https://app.example.com",
                "https://admin.example.com")
        .allowedMethods("GET", "POST")
        .allowCredentials(true);
~~~

Each request is checked against an explicit origin. Given:

~~~http
Origin: https://admin.example.com
~~~

a valid response can contain:

~~~http
Access-Control-Allow-Origin: https://admin.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

There is no standard, safe shortcut for sending literal `*` in `Access-Control-Allow-Origin` alongside credentials. Never try to work around it by disabling CORS in the browser, setting `mode: "no-cors"`, or using origin-bypass extensions: none of those work for real users.

### 6.3. When cookies/credentials are not needed

For public-data APIs requiring no client credentials, any origin may be permitted:

~~~java
registry.addMapping("/public/**")
        .allowedOrigins("*")
        .allowedMethods("GET");
~~~

In non-credentialed cases, `Access-Control-Allow-Origin: *` can be valid. The frontend should use `credentials: "omit"` when calling public APIs that need no credentials.

**Never leave a "public API" exposing sensitive data or state-changing operations without authentication.** Public CORS only declares that browsers may read responses from other origins; it does not replace security policy.

## 7. `allowedOrigins` vs. `allowedOriginPatterns`

### 7.1. `allowedOrigins`: explicit list of origins

~~~java
.allowedOrigins("https://app.example.com", "https://admin.example.com")
~~~

This is usually the easiest-to-review and safest option when trusted origins form a finite set. Values include **scheme, host, and port** (if non-default), with no path. Verify each environment carefully: dev, staging, and production use different origins.

Notes:

- `https://app.example.com` differs from `http://app.example.com`.
- `http://localhost:5173` differs from `http://localhost:3000`.
- `https://app.example.com/` with a trailing slash should not be used as a standard origin representation.
- This list is not a regex and does not support wildcard hosts like `https://*.example.com` under `allowedOriginPatterns` semantics.

### 7.2. `allowedOriginPatterns`: pattern matching that echoes the real origin

Spring Framework supports:

~~~java
.allowedOriginPatterns("https://*.example.com")
.allowCredentials(true)
~~~

Per `CorsConfiguration`, when the pattern matches `https://team.example.com`, Spring responds with:

~~~http
Access-Control-Allow-Origin: https://team.example.com
Access-Control-Allow-Credentials: true
~~~

instead of returning literal `*` or the pattern string. Thus it **can work technically with credentials**.

Pattern examples documented by the Spring API:

~~~text
https://*.example.com
https://*.example.com:[8080,8081]
https://*.example.com:[*]
~~~

These patterns can match subdomains and specified ports. This is **Spring pattern syntax**, not arbitrary regex and not path patterns. Never use `allowedOriginPatterns` just to append slashes or query strings to an origin.

**Major risk:** if any subdomain under `*.example.com` is controlled by a customer, third party, or user, that is **not a trusted origin set** merely because it shares a parent domain. A taken-over subdomain, user-content hosting subdomain, or separate tenant account could gain credentialed CORS read access.

### 7.3. Pattern `"*"` with credentials: technically accepted does not mean secure

~~~java
// Spring can match any origin and echo back the actual origin.
// NEVER USE THIS as a broad default for secret/session APIs.
.allowedOriginPatterns("*")
.allowCredentials(true)
~~~

This bypasses the check against emitting literal `*` because Spring **echoes the actual origin**. Yet it effectively means **any website can be permitted to read responses of credentialed requests** if the browser sends credentials. From a security standpoint, this is usually a severe misconfiguration for session/cookie APIs.

**Rule:** when credentials are enabled, allow only origins where you **control and fully trust all JavaScript running there**. If many tenants have separate hostnames, consider a bounded, verified allowlist in DB/config with strict ownership verification. Never reflect `Origin` unconditionally into CORS headers.

### 7.4. Do not confuse wildcards on other attributes

Per Spring Framework documentation, when `allowCredentials=true`:

- `allowedOrigins("*")`: **invalid**; use explicit origins or patterns.
- `allowedOriginPatterns("https://*.example.com")`: valid when appropriate; Spring emits **the matched origin**.
- `allowedMethods("*")`: Spring handles this by echoing the method requested in preflight rather than emitting literal `*` with credentials.
- `allowedHeaders("*")`: Spring can echo the headers requested by preflight rather than literal `*` with credentials.
- `exposedHeaders("*")`: Spring may emit literal `*` even with credentials enabled because all possible response headers are not known upfront; do not rely on that behavior when strict browser compatibility or specific header access is required.

Even when the API allows wildcards for methods/headers, **least privilege** favors listing the exact methods and headers required. In particular, never "fix CORS quickly" by turning everything into `*` without reviewing your threat model.

## 8. Runnable lab: Spring MVC, session cookies, and two localhost origins

Set up a Spring Boot 3.3.5 / Java 17 backend at `http://localhost:8080` and an HTML frontend served at `http://localhost:5173`. Different ports mean **cross-origin**, so the browser enforces CORS. However, both share hostname `localhost` and HTTP, so they are normally **same-site**: cookie demos work with `SameSite=Lax` locally without setting up complex TLS or cross-site cookie flags.

**This lab has no login and no security filters.** The session `counter` merely demonstrates a cookie round-trip. Never deploy state-changing endpoints without CSRF protection and authentication in production.

### 8.1. Project structure

~~~text
cors-credentials-demo/
├── pom.xml
├── frontend/
│   └── index.html
└── src/main/
    ├── java/com/example/corsdemo/
    │   ├── CorsDemoApplication.java
    │   ├── CorsConfig.java
    │   └── CounterController.java
    └── resources/
        └── application.properties
~~~

### 8.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cors-credentials-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

`spring-boot-starter-web` provides MVC, embedded Tomcat, and Jackson. No separate CORS library is needed; `WebMvcConfigurer` and `CorsRegistry` are part of Spring Web MVC.

### 8.3. `application.properties`

**File `src/main/resources/application.properties`:**

~~~properties
server.port=8080
server.address=127.0.0.1

# Default Servlet container session cookie used for the lab.
# Do not change to SameSite=None while using plain HTTP localhost.
server.servlet.session.timeout=20m
~~~

`server.address=127.0.0.1` binds the backend to local loopback only, avoiding accidentally exposing the port to the network. In containers/Kubernetes, binding differs; production apps need proper networking and firewalls. The default Servlet session cookie name is normally `JSESSIONID` unless customized; inspect `Set-Cookie` rather than hardcoding.

### 8.4. Spring Boot application class

**File `src/main/java/com/example/corsdemo/CorsDemoApplication.java`:**

~~~java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

### 8.5. CORS configuration: trust only frontend 5173

**File `src/main/java/com/example/corsdemo/CorsConfig.java`:**

~~~java
package com.example.corsdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
~~~

Explanation:

- `addMapping("/api/**")` applies CORS to the tested API paths without opening all endpoints.
- `allowedOrigins("http://localhost:5173")` permits **only the exact dev frontend**; `http://localhost:3000` and `http://127.0.0.1:5173` are excluded because host/port differ.
- `allowedMethods("GET", "POST")` declares the actual methods browsers may request.
- `allowedHeaders("Content-Type")` permits preflight for JSON `POST` from the frontend; CORS-safelisted headers follow browser rules.
- `allowCredentials(true)` specifies that CORS responses may be exposed when cookies/credentials are sent.
- `maxAge(1800)` permits preflight caching within browser limits; it does not cache JSON bodies.

**Do not add `@EnableWebMvc`**: use `WebMvcConfigurer` to add mappings while preserving Spring Boot's MVC auto-configuration.

### 8.6. REST controller storing a counter in `HttpSession`

**File `src/main/java/com/example/corsdemo/CounterController.java`:**

~~~java
package com.example.corsdemo;

import java.util.Map;

import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/counter")
public class CounterController {

    @GetMapping
    public Map<String, Integer> read(HttpSession session) {
        Integer count = (Integer) session.getAttribute("count");
        return Map.of("count", count == null ? 0 : count);
    }

    @PostMapping
    public Map<String, Integer> increment(HttpSession session) {
        Integer previous = (Integer) session.getAttribute("count");
        int count = (previous == null ? 0 : previous) + 1;
        session.setAttribute("count", count);
        return Map.of("count", count);
    }
}
~~~

`GET /api/counter` returns the current value without incrementing; `POST /api/counter` increments and stores it in the session. Spring MVC manages `HttpSession` and the `JSESSIONID` cookie in the browser. This illustrative counter is not atomic under concurrent `POST`s; sessions are not transactional databases.

Never expose session IDs in JSON responses, because session cookies/IDs act as bearer secrets. In a real system, state-changing `POST` endpoints **must have proper authentication/authorization and CSRF protection** when relying on cookies. This lab isolates CORS observation only; never treat it as guidance to disable CSRF in production.

### 8.7. Cross-origin frontend

**File `frontend/index.html`:**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CORS credentials demo</title>
</head>
<body>
  <h1>Testing CORS with session cookies</h1>
  <button id="read">Read counter</button>
  <button id="increment">Increment counter</button>
  <pre id="output">API not called yet.</pre>

  <script>
    const apiUrl = "http://localhost:8080/api/counter";
    const output = document.querySelector("#output");

    async function callApi(method) {
      const options = {
        method: method,
        credentials: "include"
      };
      if (method === "POST") {
        options.headers = { "Content-Type": "application/json" };
        options.body = "{}";
      }

      try {
        const response = await fetch(apiUrl, options);
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        output.textContent = JSON.stringify(await response.json());
      } catch (error) {
        output.textContent = String(error);
      }
    }

    document.querySelector("#read").addEventListener(
      "click", () => callApi("GET"));
    document.querySelector("#increment").addEventListener(
      "click", () => callApi("POST"));
  </script>
</body>
</html>
~~~

**Why does `POST` trigger preflight?** The frontend sets `Content-Type: application/json`, which is not a CORS-safelisted `Content-Type` for simple requests, so the browser sends `OPTIONS` before `POST`. `GET` adds no custom headers, so it normally skips preflight. Both requests still require valid CORS response headers.

**Why set `credentials:"include"` on both?** If the frontend omits credentials on cross-origin API calls, the browser does not send the session cookie, so each request can hit a new session or fail to read the saved counter. Even with `include`, cookies remain subject to browser policy.

### 8.8. Starting both origins

From `cors-credentials-demo`, with Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Open a second terminal in **the same root directory**. With Python 3:

~~~bash
python3 -m http.server 5173 --bind 127.0.0.1 --directory frontend
~~~

On Windows you can run:

~~~powershell
py -m http.server 5173 --bind 127.0.0.1 --directory frontend
~~~

Open exact URL:

~~~text
http://localhost:5173/
~~~

With the frontend server listening on `127.0.0.1`, `localhost` usually resolves to loopback; if your machine prefers IPv6 while the server listens only on IPv4, use `http://127.0.0.1:5173/` **and update `allowedOrigins` accordingly** because `127.0.0.1` and `localhost` are distinct origins. To avoid origin mismatches in the lab, you can pass `--bind localhost` or bind Python to the matching interface. Never open the file via `file://`, as `file:` origin/credential policies differ from normal HTTP origins.

Click **Increment counter** twice and then **Read counter**:

~~~text
POST /api/counter -> {"count":1}
POST /api/counter -> {"count":2}
GET  /api/counter -> {"count":2}
~~~

This is the result **when the browser stores and sends back the same session cookie**. Values may differ if the cookie jar already held an earlier session, if multiple tabs are open, or if concurrent requests run. Inspect DevTools Network tab to verify.

## 9. Verifying accurately with `curl`: preflight, cookies, and rejected origins

`curl` is an HTTP client and **does not enforce browser CORS policies**. Still, it is handy for checking server headers and statuses. To know whether browser JavaScript can actually read responses, test in a real browser.

### 9.1. Valid preflight

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/counter" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
~~~

When Spring MVC processes it successfully, look for equivalent headers:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
~~~

Whitespace, casing, ordering, success status (usually 200 in Spring MVC), and `Vary` header formatting can vary. Do not assert byte-for-byte text; check **header semantics**.

**Preflight does not need to send `JSESSIONID`.** With Spring Security present, ensure the CORS layer handles `OPTIONS` before authentication filters reject it.

### 9.2. Actual `POST` with a cookie jar

~~~bash
curl -i \
  -c cors-cookies.txt \
  -X POST "http://localhost:8080/api/counter" \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -d "{}"
~~~

Expect JSON containing `"count":1` for a fresh session. Inspect `Set-Cookie`, typically showing `JSESSIONID`. This `curl` command **does not run preflight automatically**; you invoked the actual `POST` independently.

Call again with the saved cookie:

~~~bash
curl -i \
  -b cors-cookies.txt \
  -H "Origin: http://localhost:5173" \
  "http://localhost:8080/api/counter"
~~~

Expect the count to persist. Do not take `curl` sending cookies as proof a browser will let JS read the response: `curl` does not enforce `SameSite`, CORS, or third-party restrictions like a browser.

### 9.3. Preflight from a rejected origin

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/counter" \
  -H "Origin: http://localhost:9999" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Spring normally rejects disallowed CORS requests (e.g., 403 "Invalid CORS request") or omits allow headers; details depend on the handling layer. What must hold is **no CORS grant is emitted** for `localhost:9999` under the lab configuration.

A `curl` request can still reach the controller unless blocked by another mechanism; that is not a CORS bug, because CORS is not a firewall.

### 9.4. Cross-origin without credentials

Temporarily edit the frontend to:

~~~javascript
fetch("http://localhost:8080/api/counter", {
  method: "GET",
  credentials: "omit"
});
~~~

Without cookies sent, the server sees a different (or uninitialized) session, so count resets to 0. That happens independently of the server still allowing origin `localhost:5173`. To restore the demo, switch back to `credentials:"include"`.

### 9.5. Intentionally testing a bad configuration

**Perform this only in an isolated test branch**, never in production:

~~~java
// INVALID config example to observe validation:
registry.addMapping("/api/**")
        .allowedOrigins("*")
        .allowCredentials(true);
~~~

When a CORS request hits it, Spring can raise an `IllegalArgumentException` regarding `allowCredentials`/wildcards or fail when validating the config. If an external proxy emits `Access-Control-Allow-Origin: *` alongside `Access-Control-Allow-Credentials: true`, the browser throws a CORS error. Fix it with an explicit origin list instead of disabling validation.

## 10. `@CrossOrigin` on a controller: when is it appropriate?

When only a single controller/method permits a distinct origin, use the annotation:

~~~java
@CrossOrigin(
    origins = "https://app.example.com",
    allowCredentials = "true"
)
@GetMapping("/api/profile")
public ProfileView profile() {
    return new ProfileView("Public display name");
}
~~~

This is an **illustrative snippet**, not a standalone Java file: `ProfileView` must be defined, placed in a `@RestController` with proper imports. Key detail: `@CrossOrigin.allowCredentials` takes the String `"true"`, unlike `CorsRegistration`'s fluent boolean `.allowCredentials(true)`.

Pattern example:

~~~java
@CrossOrigin(
    originPatterns = "https://*.trusted.example",
    allowCredentials = "true"
)
~~~

Apply only when **every matching hostname is genuinely trusted**. Never write `@CrossOrigin(allowCredentials = "true")` while omitting `origins`/`originPatterns` assuming Spring knows which origins are safe: default `@CrossOrigin` permits all origins and cannot safely combine with credentials as a wildcard.

### 10.1. Global and local CORS can combine

Spring supports global mappings on `HandlerMapping` alongside `@CrossOrigin` on controllers. Merging rules normally **combine lists additively** for allowed origins, methods, and headers, while single-valued attributes such as `allowCredentials` and `maxAge` let local override global.

Consequence: if you have global `allowedOrigins("*")` and add local `@CrossOrigin(allowCredentials="true")`, the merged result can create an invalid wildcard/credentials pairing. Never read only the annotation to infer the final policy; inspect global + local + filters + proxy configuration together.

**Maintainability tip:** in a single project, pick one clear place to configure CORS (e.g., `WebMvcConfigurer` for `/api/**`, or a Security CORS source when pre-auth execution is needed) rather than scattering overlapping settings.

## 11. Spring WebFlux: same rules, different configurer and session API

In WebFlux, use `org.springframework.web.reactive.config.WebFluxConfigurer` and `org.springframework.web.reactive.config.CorsRegistry`:

~~~java
package com.example.reactivecors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class ReactiveCorsConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
~~~

**The snippet above is complete config for a WebFlux project**, yet **must not be added to the Spring MVC project** in section 8, as they are separate stacks. To try WebFlux separately, create a second project with `spring-boot-starter-webflux` without `spring-boot-starter-web`, and add a reactive controller and matching frontend.

WebFlux controller example **standalone inside a WebFlux project**:

~~~java
package com.example.reactivecors;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/counter")
public class ReactiveCounterController {

    @GetMapping
    public Mono<Map<String, Integer>> read(WebSession session) {
        int count = session.getAttributeOrDefault("count", 0);
        return Mono.just(Map.of("count", count));
    }

    @PostMapping
    public Mono<Map<String, Integer>> increment(WebSession session) {
        int previous = session.getAttributeOrDefault("count", 0);
        int count = previous + 1;
        session.getAttributes().put("count", count);
        return Mono.just(Map.of("count", count));
    }
}
~~~

**WebFlux uses `WebSession`, not `jakarta.servlet.http.HttpSession`.** In reactive WebFlux, the default session cookie is typically named `SESSION` depending on config, not Servlet's default `JSESSIONID`. CORS credential semantics **remain identical**: `allowedOrigins("*")` is still forbidden with `allowCredentials(true)`.

For WebFlux functional routes or filter-level CORS, Spring provides `CorsWebFilter` and `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Do not confuse this reactive class with Servlet/MVC's `org.springframework.web.cors.UrlBasedCorsConfigurationSource`.

### 11.1. If an application carries both starters

In Spring Boot 3.3, if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Boot normally chooses **Servlet MVC** via auto-configuration. Using `WebClient` does not turn controllers into WebFlux. Always check which stack is running before picking `WebMvcConfigurer` vs. `WebFluxConfigurer`.

## 12. Spring Security: CORS must be processed before authentication

With Spring Security, a common failure is `OPTIONS` preflight lacking a session cookie while the security filter demands login, causing 401/403 or a redirect before CORS is evaluated.

**Principle:** place CORS handling in order **ahead of Spring Security authentication**. Spring Security integrates CORS; when using Spring MVC with MVC CORS config, enable CORS integration via:

~~~java
// Additional config snippet when the project includes Spring Security.
// This is not a standalone runnable file.
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http.cors(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}
~~~

Required imports when placed in a `@Configuration` class:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

This snippet demonstrates `http.cors(Customizer.withDefaults())`. In MVC without a separate `CorsConfigurationSource` bean, Spring Security can reuse Spring MVC's CORS configuration. With multiple `SecurityFilterChain`s or multiple CORS sources, specify the exact source per chain.

**Do not copy this snippet into the section 8 lab expecting `POST` to behave identically:** adding Spring Security activates authentication and CSRF protection. A state-changing frontend `POST` then needs a valid login/session and CSRF token, or a stateless auth design protected appropriately. **Never disable CSRF just to "clear a CORS error"** in an app using session cookies.

### 12.1. Preflight carries no cookie yet the actual request must authenticate

Example accurate sequence:

~~~text
OPTIONS /api/account  (preflight)
  -> CORS validates Origin, method, headers
  -> allowed; does NOT require JSESSIONID

GET/POST /api/account (actual)
  -> browser may attach JSESSIONID if credentials policy permits
  -> Spring Security authenticates, authorizes, validates CSRF if applicable
  -> controller/service runs
  -> response carries matching CORS headers so frontend can read it
~~~

Never treat preflight with "all unauthenticated `OPTIONS` are anonymous so reject them." Equally, never drop authentication on actual requests just because the origin is allowlisted.

### 12.2. Reactive Spring Security

With Spring Security WebFlux, use the reactive equivalents (e.g., `CorsWebFilter`/reactive CORS configuration source and `ServerHttpSecurity.cors(...)`). Never reuse Servlet `CorsFilter` or `HttpSecurity` in WebFlux. Ensure CORS runs ahead of reactive security filters and test preflight and actual requests separately.

## 13. Cookies, `SameSite`, and `Secure`: conditions independent of `allowCredentials`

Proper CORS config is only half the requirement. The browser still decides whether to send/store cookies:

| Attribute | Effect | Note |
| --- | --- | --- |
| `Domain` | Host or domain scope of cookie | A host-only cookie on `api.example.com` is not automatically sent to `other.example.com` |
| `Path` | Matching URL path prefix | A `Path=/api` cookie is not sent outside that path scope |
| `Secure` | Requires a secure connection per browser rules | Cross-site cookies with `SameSite=None` require `Secure` in modern browsers |
| `HttpOnly` | Prevents JS from reading the cookie via `document.cookie` | The browser still sends the cookie automatically per policy |
| `SameSite=Strict` | Strictly limits cookies in cross-site contexts | Can break SSO/external link navigations |
| `SameSite=Lax` | Allows some cross-site top-level navigations while blocking many cross-site subresource/fetch requests | Usually insufficient for third-party fetch cookies |
| `SameSite=None` | Permits cookies in cross-site contexts when conditions hold | Must pair with `Secure` and still obeys third-party cookie restrictions |

**Two contrasting examples:**

- `http://localhost:5173` → `http://localhost:8080`: cross-origin due to different ports, yet usually same-site; dev cookies often work with simple settings in local HTTP environments.
- `https://frontend.brand-a.example` → `https://api.brand-b.test`: cross-site. When cross-site cookies are needed, `SameSite=None; Secure` over HTTPS is usually required and still subject to browser third-party cookie limits.

No `allowCredentials=true` setting can bypass third-party cookie blocking. If an architecture depends on third-party cookies, evaluate login flows, top-level navigation, same-site deployment, token flows, or current browser policies instead of trying to respond `Access-Control-Allow-Origin: *`.

### 13.1. Do not confuse credentials with authorization

An endpoint using a bearer token explicitly attached by JavaScript as `Authorization: Bearer ...` may trigger preflight for `Authorization`:

~~~http
Access-Control-Request-Headers: authorization
~~~

Yet whether `allowCredentials(true)` is needed still depends on **how the client uses Fetch credentials mode and browser-managed credentials**. Simply having an `Authorization` header on an API does not automatically mean you must enable cookie-style credentialed CORS. Design CORS policy from the real authentication mechanism and frontend requirements.

### 13.2. Session cookies vs. reading cookies in JS

An `HttpOnly` cookie cannot be read by JavaScript via `document.cookie`, yet the browser can still send it on `fetch(credentials:"include")` when policy permits. That is usually the desired behavior for session cookies: the frontend calls the API, the server resolves the session from the cookie, and JS never touches the secret session ID.

## 14. CORS does not replace CSRF protection

A malicious page can cause the browser to send requests to an API via forms, navigations, or simple requests even when it **cannot read the response** due to CORS. With session cookies, if the browser attaches the cookie and the server executes a state-changing action, a CSRF impact still occurs.

Risk model example:

~~~text
Victim is logged into api.example.com
    |
    v
Untrusted page submits a POST to api.example.com
    |
    v
Browser attaches cookies per cookie policy
    |
    v
Server transfers funds/changes email if CSRF/auth checks are missing
    |
    v
Browser blocking JS from reading the response does not undo the transaction
~~~

Additional safeguards:

1. Use CSRF tokens for state-changing requests when relying on cookies/sessions.
2. Enforce server-side authentication and authorization, never relying on `Origin` alone.
3. Configure `SameSite` appropriately; never treat it as an unconditional replacement for CSRF protection.
4. Consider validating `Origin`/`Referer` on sensitive actions where appropriate; they are supplementary signals and can be absent in some circumstances.
5. Avoid performing important state mutations over `GET`; follow proper HTTP method semantics.
6. Enforce strict `Content-Type` and JSON parsing on APIs, while still not treating preflight as a standalone absolute CSRF barrier.

`allowCredentials=true` extends trust to JavaScript running on allowlisted origins. Therefore, allowed origins must themselves be hardened (XSS prevention, subdomain takeover checks, user-generated content isolation, third-party script control). **An XSS vulnerability on a trusted origin can leverage CORS to read authenticated API data.**

## 15. Proxies, gateways, CDNs: only one place owns CORS

In real systems, CORS may be configured in:

- Spring MVC/WebFlux (`HandlerMapping`).
- Spring Security CORS integration/filter.
- API gateway or NGINX/Ingress reverse proxy.
- CDN/edge functions.
- External middleware.

If multiple layers add:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: *
~~~

or concatenate values into a comma-separated list, browsers reject the response as invalid. **Choose one authoritative owner** to generate CORS headers or coordinate strictly so duplicates never occur.

### 15.1. Questions to check

1. Which `Origin` does the browser send to the edge? Does the edge forward `Origin` intact or alter/filter it?
2. Is `OPTIONS` preflight answered at the edge or forwarded to Spring? If the edge handles it, does the edge policy match the server's?
3. Is `Access-Control-Allow-Credentials` added for the exact routes and origins required?
4. Is `Vary: Origin` preserved in caches? Does the cache key include `Origin`/variants where needed?
5. Does the proxy rewrite `Domain`/`Path`/`SameSite`/`Secure` on `Set-Cookie` headers?
6. Does the proxy block `OPTIONS`, issue a 302 login redirect, or return 404 before requests reach Spring?
7. Do CORS headers on 401/403/500 error responses match the policy for success responses?
8. Does any layer blindly echo every `Origin` alongside `Allow-Credentials: true`? That leaks responses to untrusted websites.

CORS is a **server-to-browser response policy**, not a reason for a proxy to grant trust simply because it sees an `Origin` header. Non-browser callers can forge `Origin`; the backend requires independent authorization.

## 16. Production deployment checklist

- [ ] List exact frontend origins allowed to call the API per environment: scheme, host, port.
- [ ] With cookies/sessions, enable `allowCredentials=true` only for genuinely trusted origins.
- [ ] Never combine `allowedOrigins("*")` with `allowCredentials(true)`.
- [ ] If using `allowedOriginPatterns`, review every pattern; never use wildcards matching untrusted user/tenant subdomains.
- [ ] Never echo `Origin` unconditionally into `Access-Control-Allow-Origin`.
- [ ] Permit only methods and headers required by the API contract; avoid broad `*` when unnecessary.
- [ ] Frontend sets `credentials:"include"` when cross-origin cookies are genuinely required.
- [ ] Cookie `Domain`/`Path`/`SameSite`/`Secure`/`HttpOnly` match site topology, TLS, and browser rules.
- [ ] `OPTIONS` preflight is not mistakenly blocked by auth filters, gateways, or redirects.
- [ ] Actual requests still enforce authentication, authorization, and CSRF independently.
- [ ] Error responses also carry valid CORS headers when the frontend needs to read error details.
- [ ] No duplicate CORS headers across Spring Security, MVC/WebFlux, and proxies.
- [ ] Appropriate `Vary: Origin` for origin-dependent responses, with proper cache partitioning.
- [ ] Tested both allowed and disallowed origins in a real browser, not only with `curl`.
- [ ] Tested preflight and actual requests, with/without cookies, valid/invalid origins, HTTP and HTTPS.
- [ ] Confirmed the active stack (MVC vs. WebFlux) before selecting the configurer.

## 17. Common errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Browser: "Credential is not supported ... `*`" | `Access-Control-Allow-Origin: *` on credentialed fetch | Use explicit allowed origins, keep `allowCredentials=true` if needed |
| Spring throws `IllegalArgumentException` on credentials/wildcard | `allowedOrigins("*")` combined with `allowCredentials=true` | Fix config; do not disable validation |
| Browser reports missing `Access-Control-Allow-Credentials` | Server omitted `allowCredentials` or proxy stripped the header | Inspect actual response and effective CORS source |
| `Access-Control-Allow-Origin` missing | Origin not allowlisted or request missed the right CORS handler | Check `Origin`, route, and stack |
| Frontend uses `credentials:"include"` yet session does not persist | Cookie not sent due to `SameSite`/`Secure`/`Domain`/`Path` or third-party blocking | Inspect cookie jar/DevTools, host/scheme, and `Set-Cookie` |
| `OPTIONS` returns 401 / 302 login | Spring Security/proxy ran ahead of CORS | Enable CORS integration in order and pass preflight |
| `OPTIONS` returns 403 "Invalid CORS request" | Origin/method/header does not match policy | Compare `Request-Method`/`Request-Headers` against config |
| JSON `POST` blocked while `GET` works | `POST` triggers preflight due to JSON/custom headers | Check `OPTIONS` separately, plus allowed methods/headers |
| `POST` gets 403 after preflight succeeds | Likely CSRF or auth, not CORS | Check `SecurityFilterChain` and CSRF token |
| Browser receives multiple ACAO headers | Both Spring and gateway configure CORS | Pick a single header emitter |
| Works on localhost, fails on staging | Staging origin differs in scheme/host/port | Add the verified staging origin |
| Browser shows CORS error yet server logs 200 | Response lacks allow headers or fails cookie policy; JS cannot read | Inspect Network response/console, not just server status |
| `Access-Control-Allow-Origin: null` | Request has opaque/`null` Origin or dangerous reflection config | Disallow `"null"` origin unless strictly vetted |
| `Access-Control-Allow-Origin` contains two comma-separated URLs | Server tried to return a list in one header | Emit only the single matching calling origin |
| `@CrossOrigin` sets credentials yet global config still errors | Global/local merge can retain wildcard | Inspect combined effective config, remove wildcard |
| CORS fails only through CDN | Cache failed to split variants by `Origin`, or proxy rewrote | Check `Vary`, cache key, and edge configuration |

### 17.1. 7-step debugging workflow

1. **Identify the origin:** exact frontend URL (scheme/host/port); do not guess from the API hostname.
2. **Open DevTools Network:** inspect `OPTIONS` (if sent) and the actual request. Read `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. **Inspect preflight response:** does `Access-Control-Allow-Origin` match the origin, are `Allow-Methods/Headers` sufficient, and is `Allow-Credentials` right?
4. **Inspect actual request:** did it send cookies or `Authorization` as designed? Does the response include matching CORS headers?
5. **Inspect cookies:** `Set-Cookie`, `Domain`, `Path`, `SameSite`, `Secure`, third-party policies, `localhost` vs. `127.0.0.1`.
6. **Inspect Spring + Security + proxy:** any duplicate config, preflight blocked by auth, or mismatch between success/error CORS headers?
7. **Test negative cases:** unknown origins rejected, disallowed methods/headers rejected, API still enforces authorization and CSRF.

Browsers usually prevent JavaScript from reading detailed errors on CORS-blocked cross-origin responses. Server logs still record the true status, so **never modify business controllers before determining whether the request stopped at CORS, auth, or the proxy**.

## 18. Self-check exercises

**Q1.** Where do `https://app.example.com` and `https://api.example.com` differ in origin? What if two pages differ only in path?

**Q2.** When `allowCredentials(true)` is set, why is `allowedOrigins("*")` invalid? How does Spring handle it?

**Q3.** Why can `allowedOriginPatterns("https://*.example.com")` be used with credentials in Spring, yet still pose risks?

**Q4.** A CORS policy allows only `GET` and `POST`; the frontend sends an `application/json` `POST`. Which request may the browser send before the actual `POST`?

**Q5.** A cross-origin `GET` without preflight has its response blocked from JS by the browser. Can you be sure the server never received the request?

**Q6.** In the port 5173→8080 lab, why is `credentials:"include"` needed even though both are normally same-site?

**Q7.** The browser sends cookies with `credentials:"include"`, yet the API returns `Access-Control-Allow-Origin: *`. Can the client read the JSON response?

**Q8.** Does `allowCredentials(true)` solve `SameSite=None; Secure` and third-party cookie blocking automatically?

**Q9.** After adding Spring Security, `OPTIONS` returns 401 while internal `GET` succeeds. Which middleware ordering needs inspection?

**Q10.** An app has global `allowedOrigins("*")` and local `@CrossOrigin(allowCredentials="true")`. Why can it fail even though the controller annotation never mentions `*`?

**Q11.** An API replies `Access-Control-Allow-Origin: https://a.example, https://b.example`. Does this header validly authorize both origins?

**Q12.** Why cannot CORS replace CSRF tokens when using session cookies?

**Suggested answers:**

1. Host differs; path is not part of origin definition.
2. Browsers forbid literal `*` ACAO on credentialed responses; Spring validates this and can throw `IllegalArgumentException` when config is applied.
3. Spring echoes the specific matched origin instead of `*`. However, any matching subdomain gains credentialed read access; untrusted subdomains create risk.
4. `OPTIONS` preflight with `Access-Control-Request-Method: POST` and `Access-Control-Request-Headers: content-type`.
5. No; simple requests can be sent and processed before the browser blocks JS from reading the response.
6. `fetch` defaults to `credentials:"same-origin"`, so cross-origin (different port) does not send cookies automatically even if same-site.
7. No. Browsers block reading credentialed CORS responses with a wildcard origin.
8. No; cookie policy is an independent layer, and third-party blocking can still suppress cookies.
9. CORS must run ahead of auth; use Security CORS integration and inspect gateway/proxy layers.
10. Global/local combination may retain the wildcard, conflicting with credentials.
11. No. ACAO accepts one explicit origin or a valid wildcard, not a comma-separated list of origins.
12. Because CORS primarily restricts JS reading responses; state-changing requests can still reach the server carrying cookies per cookie policy.

## 19. Practical decision summary

| Need | Suitable CORS configuration |
| --- | --- |
| Public API needing no credentials | Can use `allowedOrigins("*")`, without `allowCredentials(true)` |
| Dedicated frontend calling session-cookie API | Explicit `allowedOrigins("https://app.example.com")`, `allowCredentials(true)`, proper cookies/CSRF |
| Finite set of multiple trusted frontends | List each explicit origin; echo only the calling origin |
| Fully controlled trusted subdomains | Can consider `allowedOriginPatterns`, auditing patterns and ownership |
| Subdomains with user-generated content or self-managed tenants | Never use a blanket wildcard with credentials; use a verified allowlist |
| Cannot verify trust of external origins | Do not open credentialed CORS broadly; redesign auth/architecture |
| Using Spring Security | Integrate CORS before auth; keep CSRF/authorization on actual requests |
| API behind gateway/CDN | Pick one CORS owner; manage `Vary` and headers across layers |

**Conclusion:** `allowCredentials(true)` is a decision to **grant JavaScript at trusted origins permission to read sensitive data**, not a quick button to silence CORS errors. For sessions and cookies, keep the allowlist small, never use `allowedOrigins("*")`, and never abuse `allowedOriginPatterns("*")` to bypass the restriction. Authentication, CSRF, cookie policy, and CORS testing must all be implemented together.

## 20. References

- Spring Framework — CORS in Spring MVC, Credentialed Requests, Global Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Framework — CORS in Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework 6.1 — `CorsConfiguration` API (`allowedOrigins`, `allowedOriginPatterns`, `validateAllowCredentials`, `combine`): https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Security — Servlet/MVC CORS integration: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Reactive WebFlux CORS integration: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- MDN — HTTP CORS and preflight: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — CORS error when using credentials with wildcard ACAO: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSNotSupportingCredentials
- MDN — Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- MDN — Access-Control-Allow-Origin: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin
- MDN — Set-Cookie, SameSite, and Secure: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie