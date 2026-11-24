# Distinguishing CORS from CSRF, routing errors, and proxy errors in Spring Boot

## 1. The problem: the browser reports "CORS error," yet the root cause can be completely different

A frontend at `http://localhost:5173` calls a Spring Boot backend at `http://localhost:8080`:

```javascript
fetch("http://localhost:8080/api/notes", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "hello" })
});
```

The browser shows "blocked by CORS policy." Is Spring Boot's `allowedOrigins` configuration wrong? **You cannot conclude that yet.** Any of the following situations can produce nearly identical symptoms:

1. Actual CORS: the backend does not permit the origin, method, request headers, or credentials.
2. `OPTIONS` preflight was rejected by Spring Security before CORS ran.
3. The backend returned **`403` due to a missing/invalid CSRF token**; the error response lacked CORS headers so the browser hid the details.
4. The frontend called the wrong URL/path/method, and the backend returned **`404` or `405`**.
5. The reverse proxy rewrote `/api` incorrectly, redirected to login/HTTPS, or blocked `OPTIONS`.
6. Nginx/gateway could not reach the backend, timed out, or the backend crashed, returning **`502`/`503`/`504`**.
7. DNS, TLS certificate, mixed-content, network, or browser-extension errors caused the request to fail at a lower layer.

**Diagnostic rule:** do not start by setting `allowedOrigins("*")` or disabling `csrf()`. Start by identifying **which request failed, who emitted the response, what the actual status/headers were, and whether the backend received the request**. CORS controls **whether browser JavaScript may read a cross-origin response**, not every category of HTTP error.

This lesson focuses on the Spring Boot web runtime with Spring MVC, Spring Security, WebFlux, and reverse proxies. It includes Spring Boot **3.5.x, Java 17+** examples, `curl` commands, `MockMvc` tests, decision matrices, and real deployment scenarios.

## 2. Four distinct layers: browser, security, router, and reverse proxy

A frontend request typically passes through multiple layers:

```text
JavaScript / Browser
   |
   | 1) checks origin, sends preflight when needed,
   |    enforces CORS policy after receiving response
   |
   v
DNS / TLS / CDN / Nginx / Ingress / API Gateway
   |
   | 2) selects host/path, routes upstream,
   |    terminates TLS, timeouts, URI rewrites,
   |    gateway auth/rate limits
   |
   v
Spring Security filter chain
   |
   | 3) CORS integration, authn/authz, CSRF,
   |    security headers, sessions
   |
   v
Spring MVC DispatcherServlet / WebFlux HandlerMapping
   |
   | 4) matches path, HTTP method, consumes/produces,
   |    binds arguments, executes controller
   |
   v
Service / Database / Downstream
   |
   v
HTTP response returns through proxy -> Browser
   |
   +--> Browser may hide response if CORS fails
```

These layers **do not replace each other**:

| Mechanism | Primary question | Where typically handled? | Related symptoms |
| --- | --- | --- | --- |
| **CORS** | May a script from origin A access a response from origin B? | Enforced by browser; server emits allow headers | Console CORS error, `OPTIONS` preflight, missing `Access-Control-Allow-Origin` |
| **CSRF protection** | Is a state-changing request carrying browser-attached cookies an intentional user action? | Server / Spring Security | Usually `403 Forbidden` when token is missing/invalid |
| **Authentication/authorization** | Who is the caller, and do they have permission for the resource? | Spring Security / gateway | `401`/`403`, redirect to login |
| **Routing/mapping** | Do method and path match an endpoint? | Proxy router, Spring MVC/WebFlux | `404`, `405`, `415`, `406` |
| **Reverse proxy/upstream** | Can the request be forwarded to a healthy backend? | Nginx, Ingress, LB, API Gateway | `502`, `503`, `504`, redirects, gateway 404 |
| **Network/TLS** | Can a valid, secure connection reach the endpoint? | DNS, TCP, TLS, browser/OS | Connection refused, DNS/TLS error, mixed content |

A **`403` status does not automatically mean CSRF**, because the CORS processor can return 403, authorization can return 403, and a gateway/WAF can block requests too. A **`404` status does not automatically mean the controller is wrong**: a gateway or proxy can emit 404 before the request ever reaches Spring.

## 3. What does CORS actually do?

### 3.1. Origin is scheme + host + port

An `Origin` typically looks like:

```text
http://localhost:5173
https://app.example.com
https://app.example.com:8443
```

Two URLs have different origins when they differ in **scheme, hostname, or port**:

| Open page | API called | Same-origin? | Need to check CORS for browser fetch? |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:8080` | No, different port | Yes |
| `https://app.example.com` | `https://api.example.com` | No, different host | Yes |
| `https://app.example.com` | `http://app.example.com` | No, different scheme | Yes; may also be blocked by mixed content |
| `https://app.example.com` | `https://app.example.com/api` | Yes | Usually no cross-origin CORS |
| `http://localhost:5173` | `http://127.0.0.1:8080` | No, different hostname and port | Yes |

**Same-origin differs from same-site.** Two subdomains `app.example.com` and `api.example.com` may belong to the same *site* under `SameSite` cookie rules yet still be **cross-origin** and require CORS. CORS does not control cookie `Domain`/`Path`/`Secure`/`SameSite`.

### 3.2. The browser decides—the server does not "open network access"

A `GET` response can be returned properly by the backend with `200 OK`. Yet if the request is cross-origin and the browser receives no valid `Access-Control-Allow-Origin`, JavaScript is **forbidden from reading the response**. The HTTP request **may already have reached the server and run**; a Console CORS message does not mean the controller never executed.

`curl` and Postman do not enforce browser CORS policy. Therefore:

- `curl` can receive a 200 body while browser scripts are blocked.
- `curl -H "Origin: ..."` helps inspect **headers emitted by the server**, yet does not prove the browser will actually let JavaScript read the body.
- Direct server-to-server calls do not need CORS, though they still require auth, network policies, TLS, and permission checks.

### 3.3. Key CORS response headers

| Header | Meaning |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin allowed to read the response, or `*` in certain non-credentialed cases |
| `Access-Control-Allow-Methods` | HTTP methods allowed in **preflight** |
| `Access-Control-Allow-Headers` | Request headers allowed in **preflight** |
| `Access-Control-Allow-Credentials: true` | Lets the browser expose the response when a cross-origin request uses credentials, provided a specific origin is accepted |
| `Access-Control-Max-Age` | How long the browser may cache the **preflight** result (subject to browser caps) |
| `Access-Control-Expose-Headers` | Additional response headers JavaScript may read |
| `Vary: Origin` | Helps caches distinguish response headers when CORS depends on `Origin` |

**Never** send `Access-Control-Allow-Origin: *` together with `Access-Control-Allow-Credentials: true` when the frontend sends credentialed CORS requests. Browsers reject that combination. With credentials, configure **explicit origins**, such as `http://localhost:5173`, and evaluate how trustworthy that origin is.

`Access-Control-Allow-Origin` is not a comma-separated list of multiple origins; each response should carry at most one valid origin (or wildcard when allowed). Never let Spring and Nginx **both add two `Allow-Origin` headers**, resulting in duplicate/invalid values.

### 3.4. CORS is not authentication

Letting `https://frontend.example.com` read an API does not prove a user is logged in. Tokens/sessions and authorization must still be enforced separately. Conversely, a request with a valid token can still have its response hidden by the browser if the CORS policy is wrong.

Never use `Origin` as proof of user authentication. Non-browser clients can set `Origin` arbitrarily; the server must never grant data access solely because the `Origin` string matches an allowlist.

## 4. `OPTIONS` preflight: how to recognize it and why it often fails

### 4.1. When is preflight sent?

Browsers send a **CORS preflight request** ahead of the actual request whenever the method, `Content-Type`, or custom headers fall outside the CORS-"safelisted" set. For instance, a `POST` with `Content-Type: application/json` and `X-CSRF-TOKEN` normally requires preflight:

```http
OPTIONS /api/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

An allowing response can look like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

This is an **illustrative** response; success status may be 200 or 204 depending on server/framework, and exact headers/ordering depend on config. The browser sends the actual `POST` only after preflight passes.

### 4.2. Preflight usually carries no authentication cookies

`OPTIONS` preflight is a permission-check request sent by the browser. **It does not carry session authentication cookies** under standard CORS rules. If Spring Security requires login **before processing CORS**, preflight gets blocked with `401` or redirected, even when the actual request has a valid cookie.

Spring Security recommends handling CORS **before** cookie-dependent authentication checks; the common way is `http.cors(...)` with a suitable CORS configuration source. Never "fix" preflight by disabling all authentication or CSRF across the API.

### 4.3. An arbitrary `OPTIONS` request is not necessarily a preflight

Running:

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes
```

does **not** fully simulate a CORS preflight, because it lacks `Origin` and `Access-Control-Request-Method`. Send the right headers instead:

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

With the section 9 demo configuration, this returns a successful preflight response with `Allow-Origin`. If you get 401/403/404/405/redirect, determine **which layer** handled `OPTIONS` and why.

### 4.4. "Simple requests" do not guarantee CSRF safety

An HTML form `POST` with `application/x-www-form-urlencoded` may **skip** preflight while still attaching the user's session cookies per browser policy. That is why **CORS does not replace CSRF protection**.

Dropping JSON `Content-Type` or custom headers to avoid preflight only hides a symptom; it does not fix access controls, API correctness, or CSRF risk. Design endpoints with clean contracts and explicit security configuration.

### 4.5. A passing preflight does not guarantee the actual request succeeds

Suppose a CORS filter handles `OPTIONS /api/missing` for all of `/api/**` ahead of Spring MVC routing: preflight can return **200**, yet `GET /api/missing` still returns **404** because the route does not exist. Likewise, a `POST` preflight can return 200 while the actual `POST` missing a CSRF token returns **403**.

Always test **both preflight and the actual request**. Never take a lone `OPTIONS 200` as proof the API works end-to-end.

## 5. CSRF: differs from CORS in both goal and timing

**Cross-Site Request Forgery (CSRF)** exploits the browser automatically attaching credentials (especially session cookies) when sending requests to an application where the user is logged in. Another site can trick the browser into performing an unintended action.

For example, a banking app exposes a data-mutating endpoint:

```http
POST /api/transfer
Cookie: SESSION=...
Content-Type: application/x-www-form-urlencoded

amount=100&to=attacker
```

If the API relies solely on the session cookie without checking origin or CSRF tokens when needed, a request triggered by another page can cause side effects. The browser **does not need to let external scripts read the response** for the side effect to happen. **CORS governs JavaScript's ability to read responses; CSRF protects against executing state-changing actions.**

### 5.1. Spring Security and 403 status codes

In the default Spring Security Servlet setup, CSRF protection is enabled for **unsafe** methods (typically `POST`, `PUT`, `PATCH`, `DELETE`). A `POST` missing a token or carrying an invalid token is rejected with **403 by `CsrfFilter`**, even when:

- The request is same-origin;
- CORS is configured completely accurately;
- The user is authenticated;
- The endpoint exists and the HTTP method matches.

Conversely, `GET` normally does not require a CSRF token; **`GET` must never mutate critical data**. If `GET` transfers money or deletes records, that is an API design flaw that undermines protection.

### 5.2. Why can a 403 response look like a CORS error?

Two scenarios:

1. **403 with matching `Allow-Origin`**: cross-origin scripts can read the 403 response and the frontend handles the error cleanly.
2. **403 without matching `Allow-Origin`**: the browser hides the body/status from JS and reports CORS. The root cause can still be CSRF, auth, or a WAF.

Therefore check the Network response, server security logs, and actual headers—never guess from the Console message alone.

### 5.3. A valid CORS policy does not replace CSRF tokens

- `Access-Control-Allow-Origin` declares which origins JS may read responses from, **not** an anti-forgery token.
- Cookie `SameSite=Lax`/`Strict` helps mitigate certain cross-site requests yet is insufficient to eliminate all CSRF.
- A subdomain can be same-site without being trustworthy; CSRF still requires threat modeling.
- Credentialed CORS increases the trust placed in permitted origins; it never eliminates CSRF requirements.
- If an API accepts only JS-attached Bearer tokens in `Authorization` without browser auto-sent cookies, the CSRF risk profile differs. **Never disable CSRF merely because an endpoint returns JSON**; evaluate your exact credential mechanism.

### 5.4. Fetching and sending back the CSRF token

With Spring Security + HTTP sessions, you can expose `GET /api/csrf` to provide the CSRF token to the browser. The frontend sends the token in a header (such as `X-CSRF-TOKEN`) or form parameter while retaining the session cookie:

```javascript
const api = "http://localhost:8080";
const csrfResponse = await fetch(api + "/api/csrf", {
  credentials: "include"
});
const { headerName, token } = await csrfResponse.json();

const response = await fetch(api + "/api/notes", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [headerName]: token
  },
  body: JSON.stringify({ text: "hello" })
});
const result = await response.json();
console.log(response.status, result);
```

This is a **snippet running inside a browser module/async context**, not a standalone HTML file. Assuming the page runs at `http://localhost:5173`, the backend runs the section 9 demo, and the browser supports cookies and CORS credentials, the real result when valid is status 200 and JSON `{"saved":"hello"}`. Tokens can rotate across sessions; after login/logout, fetch a fresh token.

**Important:** cross-site SPAs relying on cookies are constrained by `SameSite`, `Secure`, and third-party cookie policies. Passing `credentials:"include"` does not override those constraints.

## 6. Routing in Spring Boot: 404, 405, 415, and 406 are not default "CORS errors"

### 6.1. Controller mappings

Example:

```java
@RestController
@RequestMapping("/api")
class DemoController {
    @GetMapping("/ping")
    String ping() { return "pong"; }

    @PostMapping(path="/notes", consumes="application/json")
    String create(@RequestBody String body) { return body; }
}
```

This is an **illustrative class**, requiring Spring MVC imports and placement in a scanned package. Combined mappings are:

- `GET /api/ping`;
- `POST /api/notes` accepting `application/json`.

Typical outcomes:

| Request | Typical result | Cause |
| --- | --- | --- |
| `GET /api/ping` | `200` | Matches path and method |
| `GET /api/pinng` | `404` | Misspelled path |
| `GET /api/notes` | `405` | Path mapped, yet `GET` is unsupported |
| `POST /api/notes` with `Content-Type: text/plain` | `415` | Controller requires JSON |
| `GET` endpoint with `produces` constraint mismatching `Accept` | `406` | No compatible media type |
| `POST /api/notes` missing CSRF token (with Security enabled) | Often `403` **before routing/deserialization** | Security filter blocks ahead of Controller |
| `OPTIONS` preflight lacking CORS config | Often 403/4xx | CORS processor/filter or upstream layer rejects |

Actual statuses depend on security filters, exception handlers, proxies, and configuration; this table is not a universal guarantee across every project. For instance, if auth runs before routing, even a nonexistent URL can return 401/403 instead of 404.

### 6.2. Specific routing pitfalls

- Missing context path: backend actually runs at `/shop/api/ping` while frontend calls `/api/ping`.
- Wrong proxy prefix: proxy exposes `/backend/api/ping` yet forwards to `/api/ping` or `/ping`.
- Trailing slash: `/api/users` and `/api/users/` are not automatically treated as equivalent in modern Spring Framework releases.
- Wrong HTTP method: frontend sends `PUT` while controller defines only `@PostMapping`.
- `consumes`/`produces` mismatching `Content-Type`/`Accept`.
- Controller placed outside component-scan scope, so the route is never registered.
- Requests going to the actuator/management port or an API gateway mapping the wrong service.
- Security failing before routing runs, misleading you into thinking the controller does not exist.

### 6.3. Tracing the request route

Spring MVC routes via `DispatcherServlet` and `RequestMappingHandlerMapping`. If a request **reached Spring** with no matching handler, logs/exceptions show `NoHandlerFoundException`, `NoResourceFoundException`, or `HttpRequestMethodNotSupportedException` depending on version/config.

If the request **never reached Spring**, editing `@GetMapping` achieves nothing. Inspect reverse proxy, ingress, and Spring access logs.

Never add a catch-all `@RequestMapping("/**")` just to "handle CORS" when the real issue is a wrong route. That hides legitimate 404s and can break static resources.

## 7. Reverse proxies, gateways, and status codes emitted ahead of the backend

### 7.1. Common failures

| Status / symptom | Possible source | Characteristics |
| --- | --- | --- |
| `301`/`302`/`307`/`308` | Proxy or application redirect | Preflight/credentials can fail on redirects, especially when changing origin or scheme |
| `401 Unauthorized` | Authentication filter, gateway auth, proxy auth | Unauthenticated or missing credentials |
| `403 Forbidden` | Authorization, CSRF, CORS filter, WAF | Distinguish via headers, logs, and request type |
| `404 Not Found` | Spring route or gateway route | Request may never have reached the app |
| `405 Method Not Allowed` | Spring mapping or gateway policy | Right path, wrong method |
| **`502 Bad Gateway`** | Proxy received invalid upstream response or connection failed | Backend down, wrong port, upstream TLS/HTTP mismatch |
| **`503 Service Unavailable`** | Gateway or backend | No healthy upstream, overload, maintenance |
| **`504 Gateway Timeout`** | Proxy waited too long for upstream | Slow backend/DB, timeouts, network issue |
| `413 Content Too Large` | Proxy or server | Body exceeds limit |
| `431 Request Header Fields Too Large` | Proxy or server | Headers/cookies too large |
| TLS/DNS/connection failure | Network stack, certificate, browser | May have **no HTTP status** because no response was produced |

`502`/`503`/`504` usually come from gateways, though a backend can also return 503 deliberately; never attribute a status code to one component without inspecting logs and `Server`/`Via` headers.

### 7.2. Nginx can break paths even when CORS is right

Suppose Spring has `GET /api/ping`, and a public proxy listens on port 8088. **Illustrative local HTTP Nginx config**:

```nginx
server {
    listen 8088;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
```

Because `proxy_pass` here **has no URI path** after host/port, Nginx normally preserves the request URI: `GET /api/ping` arrives upstream as `/api/ping`.

If changed to:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

The **trailing** slash in `proxy_pass .../;` specifies the URI prefix `/`. Under Nginx rewrite rules, the `/api/` part matching `location` is replaced with `/`, turning `/api/ping` into `/ping` upstream. The Spring controller expecting `/api/ping` returns **404**, even though CORS had nothing wrong.

This is why you must inspect **both the external proxy URL and the URI actually received by the backend**.

### 7.3. `OPTIONS` can be blocked before reaching Spring

Nginx/Ingress/Gateway can:

- Reject `OPTIONS` via allowed-methods or auth policies.
- Redirect HTTP to HTTPS or `/api` to `/api/`.
- Strip/overwrite `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
- Handle preflight itself yet omit `Access-Control-Allow-Headers`.
- Add a second `Access-Control-Allow-Origin` while Spring also adds one.
- Return `502`/`504` without CORS response headers, making the browser display only "CORS failed."

When CORS is handled at the proxy **instead of the backend**, design one clear owner and ensure preflight, actual responses, and error responses stay consistent. Never stack two "add CORS to every response" layers blindly.

### 7.4. Forwarded headers do not fix everything

Behind TLS termination, a proxy can send `Forwarded` or `X-Forwarded-Proto` and `X-Forwarded-Host` so the backend builds right URLs and redirects. Spring Boot supports `server.forward-headers-strategy` (e.g., `framework` for `ForwardedHeaderFilter` in Servlet MVC).

```properties
# Enable only when the backend truly sits behind a trusted proxy.
server.forward-headers-strategy=framework
```

This helps redirect schemes and hosts, yet **cannot fix** a bad `proxy_pass`, open a closed backend port, or fix OAuth callbacks or CORS origin allowlists. Ensure Internet clients **cannot inject forged forwarded headers** into trusted paths; proxies must strip/overwrite headers.

### 7.5. Testing directly vs. through the proxy

```bash
# Direct to backend:
curl -i http://localhost:8080/api/ping

# Through proxy in front of backend:
curl -i http://localhost:8088/api/ping
```

If direct returns 200 while proxied returns 404/502, focus on gateway routes, rewrites, DNS/upstream ports, and logs. If both return 404, inspect Spring mappings and context path. When comparing CORS, include the exact same `Origin` on both requests.

In containers/Kubernetes, `localhost` inside **the proxy container/pod** does not point to another Spring Boot container. Use the runtime's service DNS/name/port. The addresses above illustrate only two processes on the same local host.

## 8. Evidence-first diagnostic workflow

### Step 1 — Identify the failing request

Open DevTools → **Network**, filter `Fetch/XHR`, and check:

- Actual Request URL (scheme, hostname, port, path, query).
- Request Method: `OPTIONS` or actual `GET`/`POST`/`PUT`?
- Status code if visible to the browser.
- Request headers: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, `Cookie`, `Authorization`.
- Response headers: `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Vary`, `Location`, and signs of proxy-generated responses.
- Timing: DNS, connect, TLS, waiting, failed/canceled.

**Console is a symptom; Network + logs are evidence.** A single `TypeError: Failed to fetch` line can mask CORS, TLS, and network errors—never treat it as the whole diagnosis.

### Step 2 — Separate preflight from the actual request

If the browser sent `OPTIONS` and never sent the actual request, focus on **preflight**. If `OPTIONS` succeeded yet `POST` failed, focus on **CSRF/auth/routing/validation/proxy** on the actual request.

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Use the **exact origin** of the real page (including port) and the **exact headers/method** of the actual request. A `GET` preflight test does not prove a `POST` with `Authorization` will pass.

### Step 3 — Send the actual request, see the real status

```bash
curl -i http://localhost:8080/api/ping \
  -H "Origin: http://localhost:5173"
```

If HTTP status is 200 yet `Allow-Origin` is missing, it is a CORS response policy issue. If it is 403/404/502, determine the underlying HTTP cause first, then check CORS headers. `curl` does not block reading the response like a browser.

### Step 4 — Compare hop by hop

With the same method/path/`Origin`:

- Call the backend directly (if network and permissions permit).
- Call the public ingress/gateway.
- Compare `status`, `Location`, `Access-Control-*`, `Server`/`Via`, and request IDs.
- Where they differ, inspect rewrites, routes, filters, or headers at the hop that changed the outcome.

Never share real cookies, Bearer tokens, session IDs, or CSRF tokens in public logs while collecting evidence.

### Step 5 — Locate how far Spring processed the request

- **No request in backend access log**: suspect proxy, DNS/upstream, TLS, load balancer, or routing.
- **Request in access log, yet controller did not run**: suspect CORS filter, security/CSRF, handler mapping, or pre-controller exceptions.
- **Controller ran and returned 5xx**: suspect service/database/serialization, and check external proxy timeouts.
- **Controller returned 200, yet browser fails CORS**: inspect response headers at the client-facing proxy, duplicates, and credentials.
- **Server returned 404/405**: check path, method, context path, and component scanning.

### Step 6 — Fix the right layer and re-verify

Never disable security/filters "to let traffic through for testing." Fix the origin allowlist, security chain, controller mapping, or proxy route **where the error actually occurred**. Then re-test **preflight + actual request + browser behavior**, and confirm disallowed origins remain blocked.

## 9. Complete demo: Spring Boot MVC + Spring Security + CORS and CSRF

This demo lets you observe four distinct behaviors on one server:

1. Allowed-origin `OPTIONS` preflight succeeds without a session.
2. `GET /api/ping` returns JSON with CORS headers when given a valid `Origin`.
3. `POST /api/notes` **without a CSRF token** returns `403` even though CORS permits it.
4. The same `POST` **with a session cookie and valid CSRF token** succeeds.
5. `GET /api/missing` returns `404`; `GET /api/notes` returns `405` even though CORS is allowed.

Uses **Java 17+**, **Maven**, and **Spring Boot 3.5.0** (an existing 3.5 release). The demo version is pinned for reproducibility; production should run a maintained patch release. The demo **permits all requests at the authorization layer** to isolate CORS/CSRF; **do not** treat this as a security policy for real APIs.

### 9.1. Structure

```text
cors-diagnosis-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/corsdemo/
    │   │   └── CorsDiagnosisApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/corsdemo/
            └── CorsDiagnosisTest.java
```

### 9.2. Complete `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cors-diagnosis-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

The Spring Boot parent manages Spring dependency versions; do not pin `spring-security-web` or `spring-webmvc` separately. `spring-security-test` lets `MockMvc` simulate valid CSRF tokens in tests.

### 9.3. Complete Java source: controller + security config

Single file `src/main/java/com/example/corsdemo/CorsDiagnosisApplication.java`:

```java
package com.example.corsdemo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDiagnosisApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class DemoApiController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    // Call GET to retrieve a token matching the current session.
    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken token) {
        return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken());
    }

    @PostMapping(path = "/notes",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> create(@RequestBody NoteInput input) {
        return Map.of("saved", input.text());
    }

    public record NoteInput(String text) {}
}

@Configuration
class WebSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Demo frontend origin; different origin from port 8080.
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().permitAll())
                .build();
    }
}
```

This is a valid single Java file: only `CorsDiagnosisApplication` is a `public` top-level class, while `DemoApiController` and `WebSecurityConfig` in the same package are scanned by Spring. `record NoteInput` is a valid request type with Java 17 and Jackson from the web starter.

**Key explanation:**

- `UrlBasedCorsConfigurationSource` registers the policy for `/api/**`.
- `http.cors(Customizer.withDefaults())` integrates CORS at the right position in the Spring Security filter chain so preflight is not treated like a normal unauthenticated request.
- `.csrf(Customizer.withDefaults())` **keeps CSRF enabled**. It is independent of CORS.
- `.anyRequest().permitAll()` **only disables authorization checks in the demo**, not `CsrfFilter`. Thus a `POST` lacking a token still returns 403.
- `GET /api/csrf` loads the token into the session when needed; the browser/`curl` must retain the session cookie so `POST` uses the matching token.
- `setAllowCredentials(true)` is valid only with explicit configured origins, never wildcard `*`.
- `setMaxAge(1800L)` is **preflight** cache duration in seconds, not session timeout or JWT lifetime.
- Do not manually register a second `CorsFilter` or scatter `@CrossOrigin("*")` across controllers; multi-layer settings easily emit duplicate headers.

**Limitation:** The demo has no login and only echoes the "note" in the response; there is no database. The goal is observing request flow, not building storage or production auth.

### 9.4. `application.properties`

```properties
server.port=8080
spring.application.name=cors-diagnosis-demo
```

This is the complete basic config file. CORS policy and `SecurityFilterChain` live in Java config. If port 8080 is busy, change `server.port` and update test URLs.

### 9.5. Running

From `cors-diagnosis-demo`, requiring Java 17+ and Maven:

```bash
mvn clean package
java -jar target/cors-diagnosis-demo-1.0.0.jar
```

You can use `mvn spring-boot:run` during development. Once started, you do not need a frontend actually running on 5173 to test CORS with `curl`: the server inspects only the `Origin` header sent in the request.

### 9.6. Testing the `GET` route and CORS

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/ping
```

Key expected elements:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"status":"ok"}
```

This is an **illustrative partial response**: header ordering, exact headers, and HTTP reason phrase vary by servlet container and version; the JSON body has key `status` with value `ok`. A credentialed browser fetch from origin 5173 can read the response if cookie policies and other rules allow.

Try a disallowed origin:

```bash
curl -i -H "Origin: https://not-allowed.example" \
  http://localhost:8080/api/ping
```

The CORS processor in the demo config rejects this origin; the status is typically **403** with "Invalid CORS request." Never fix this by adding all origins when the design intends only one frontend.

### 9.7. Testing preflight before JSON `POST`

```bash
curl -i -X OPTIONS http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
```

Expect preflight success (typically HTTP 200), with `Access-Control-Allow-Origin: http://localhost:5173`, `Access-Control-Allow-Methods` containing `POST`, `Access-Control-Allow-Headers` allowing `content-type` and `x-csrf-token`, and `Access-Control-Allow-Credentials: true`. **No cookie or CSRF token is needed on preflight**.

### 9.8. `POST` without token: CSRF error, not an origin error

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  --data '{"text":"demo"}'
```

Expect **403 Forbidden** due to missing CSRF token. CORS allowed the origin, yet Spring Security blocked the unsafe operation. A 403 response carrying a valid `Access-Control-Allow-Origin` lets the browser inspect the real status instead of masking it behind a CORS error.

### 9.9. `POST` with valid token: distinguishing which layer fixed it

First fetch the token and session cookie:

```bash
curl -i -c cookies.txt -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/csrf
```

JSON body format:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "<session-specific-token-value>"
}
```

The angle-bracketed string is a **placeholder description**, not literal output to copy. Take the real `token` value from the response and send it in the next request's header along with the same cookie jar:

```bash
curl -i -b cookies.txt -X POST http://localhost:8080/api/notes \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: PASTE_ACTUAL_TOKEN_HERE" \
  --data '{"text":"demo"}'
```

Replace `PASTE_ACTUAL_TOKEN_HERE` with the token from that session. When valid, response:

```http
HTTP/1.1 200
Content-Type: application/json

{"saved":"demo"}
```

This is a shortened illustrative response. In Spring Security 6, tokens returned via `CsrfToken` may be **masked** to mitigate BREACH; use the returned value verbatim without altering or re-hashing it. If the token does not match the session cookie, the request still gets 403—which is the intended protection.

To avoid extracting the token manually, combine `curl` with a JSON tool like `jq` or use the browser fetch snippet from section 5.4.

### 9.10. Testing route and method errors

```bash
curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/missing

curl -i -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/notes
```

With the demo config: the first returns **404**, and the second returns **405** because `/api/notes` accepts only `POST`. Valid `Access-Control-Allow-Origin` may still be present, yet it does not turn a wrong route into a valid one.

Note when using unsafe methods to test 405: Spring Security may reject CSRF **before** routing, returning 403 instead of 405. Using `GET` (safe) against a `POST`-only route makes the test clearer.

### 9.11. Note on shells

The example commands use Bash/Linux/macOS with `\` for line continuation. In PowerShell, use `curl.exe` and put the command on one line or use PowerShell line-continuation syntax; JSON quoting may also need adjustment. On Windows, Postman or another header-capable HTTP client is another option.

Never run commands containing real tokens/cookies on shared terminals or paste command history/logs publicly. The demo contains no production credentials.

## 10. `MockMvc` testing: separating CORS, CSRF, and routing

Two test dependencies are already in section 9's POM:

- `spring-boot-starter-test`: JUnit Jupiter + Spring Test/`MockMvc` and test utilities;
- `spring-security-test`: request post-processors such as `csrf()`.

Complete file `src/test/java/com/example/corsdemo/CorsDiagnosisTest.java`:

```java
package com.example.corsdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsDiagnosisTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightSucceeds() throws Exception {
        mvc.perform(options("/api/notes")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "http://localhost:5173"));
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"demo\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/api/notes")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"demo\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.saved").value("demo"));
    }

    @Test
    void wrongRouteIsNotFound() throws Exception {
        mvc.perform(get("/api/missing"))
            .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodIsNotAllowed() throws Exception {
        mvc.perform(get("/api/notes"))
            .andExpect(status().isMethodNotAllowed());
    }
}
```

Run:

```bash
mvn test
```

The tests are independent and share no cross-request session state. `MockMvc` runs through the Spring Security filter chain when configured as above. Do not claim these tests verify the full reverse proxy: **`MockMvc` does not pass through Nginx/CDN**, so HTTP integration smoke tests against the real deployment path are still required.

## 11. Proper ways to configure CORS in Spring MVC

Spring MVC has several configuration points; pick one clear mechanism and make sure Spring Security sees that policy.

### 11.1. `@CrossOrigin` for one controller

```java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {RequestMethod.GET, RequestMethod.POST})
@RestController
@RequestMapping("/api/public-info")
class PublicInfoController {
    @GetMapping
    String read() { return "ok"; }
}
```

This is an **illustrative snippet**, requiring `CrossOrigin`, `RequestMethod`, `RestController`, `RequestMapping`, and `GetMapping` imports. When Spring Security is present, **integrate** the policy with the filter chain. Never slap `@CrossOrigin` onto unrelated endpoints just to "clear Console errors."

### 11.2. `WebMvcConfigurer#addCorsMappings`

```java
@Configuration
class CorsMvcConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
```

This is an **MVC configuration snippet**, requiring matching imports. It can be paired with `http.cors(Customizer.withDefaults())` so Spring Security uses MVC CORS. **Do not add this fragment alongside the demo's `corsConfigurationSource` bean** expecting everything to merge as you wish; when multiple CORS sources or filter chains exist, bean/mapping selection can get complex. Use one clear source and test it.

### 11.3. CORS filter in Spring Security

A `UrlBasedCorsConfigurationSource` supplying policy to `SecurityFilterChain` makes processing order explicit, especially with multiple endpoints or security chains. Section 9's example uses this approach. With multiple `SecurityFilterChain`s, verify the CORS source and path matchers of **each chain** rather than assuming one config unconditionally covers every path.

**Never configure** `allowCredentials(true)` with `allowedOrigins("*")`. If dynamic configured origins are genuinely required, Spring supports `allowedOriginPatterns`, yet patterns must be tightly scoped, tested, and security-reviewed—never use broad patterns on sensitive cookie/session APIs.

### 11.4. CORS in WebFlux

Spring WebFlux supports CORS via `WebFluxConfigurer`/`CorsWebFilter` and reactive `HandlerMapping` infrastructure. **WebFlux-specific snippet**:

```java
@Configuration
class CorsWebFluxConfig implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type")
                .allowCredentials(true);
    }
}
```

Imports must come from `org.springframework.web.reactive.config.WebFluxConfigurer` and `org.springframework.web.reactive.config.CorsRegistry`. With **Spring Security WebFlux**, integrate CORS through `SecurityWebFilterChain`/`CorsWebFilter`; never copy Servlet MVC's `HttpSecurity`/`SecurityFilterChain` into the reactive runtime. Reactive CSRF has its own support and policy as well.

## 12. Browser `fetch`, cookies, `Authorization`, and credential traps

### 12.1. Cross-origin `fetch` does not send cookies automatically like same-origin

Default `fetch` credentials mode is normally `same-origin`. If an SPA at `http://localhost:5173` calls an API at `http://localhost:8080` and needs cookies/sessions, the frontend uses:

```javascript
fetch("http://localhost:8080/api/ping", {
  credentials: "include"
});
```

The server must permit the explicit origin alongside `Access-Control-Allow-Credentials: true`. However, **cookies must still satisfy** `Domain`/`Path`/`Secure`/`SameSite`/browser privacy policies. `credentials:"include"` cannot override third-party cookie rules and will not fix a server 401/403.

### 12.2. CORS does not mean "accept any request with `Authorization`"

When sending `Authorization: Bearer ...`, browsers normally trigger preflight because the header is not safelisted; the server must allow `Authorization` in `Access-Control-Allow-Headers` if the API uses it. In addition, the backend **must still verify the token and permissions**.

Section 9's demo permits only `Content-Type`/`X-CSRF-TOKEN`, **deliberately omitting `Authorization`**. If you add a Bearer token on the frontend without updating the CORS header allowlist, preflight fails even though the endpoint and cookies are fine. Update the policy deliberately when changing the contract and add tests.

### 12.3. Masked 401/403 problems

Suppose an API returns `401` and redirects to `/login`, yet the login page lacks CORS headers. JS sees a CORS error instead of an auth failure. Better practices are:

- Have APIs return `401`/`403` statuses with proper CORS response headers for allowed origins;
- Have the frontend handle auth errors from JSON/status instead of redirecting API fetches to a cross-origin HTML login page;
- Keep gateway and Spring aligned on one error-response strategy;
- Never open CORS to all origins just to "read errors" when data is sensitive.

### 12.4. Never use `mode:"no-cors"` to fix errors

```javascript
fetch("https://api.example.com/private", { mode: "no-cors" });
```

The result is an **opaque response** where JavaScript cannot read normal status, body, or headers. This is not how you make cross-origin JSON APIs work. Fix CORS on the server/proxy or serve from the same origin via a reverse proxy.

## 13. Security and caching while fixing CORS/proxies

### 13.1. Why not enable wildcards everywhere?

When an API returns personal data tied to cookies/sessions, permitting arbitrary origins with credentials can let untrusted sites read user data (where browser cookie policies allow). That is a major security policy change, not a small network tweak.

An allowlist should reflect the **actual frontend origins** per environment (dev, staging, production); never accept arbitrary hostnames with similar suffixes. For origins loaded from config/environment, validate exact scheme and port and never assemble them from an untrusted request `Host`.

### 13.2. `Vary` and caching

When a server selects `Access-Control-Allow-Origin` from the `Origin` header, shared caches must avoid mixing headers/data across origins. `Vary: Origin` plus relevant preflight headers helps caches differentiate variants. A reverse proxy/CDN adding CORS headers itself may strip or overwrite `Vary` improperly, causing intermittent browser failures.

**Never** treat `Vary: Origin` as authorization. Personal data still requires `Cache-Control: private` or `no-store` per data sensitivity, alongside server-side permission checks.

### 13.3. Do not disable CSRF globally to bypass 403

When a backend uses cookie sessions or browser-auto-sent HTTP Basic auth, CSRF protection matters. Disable CSRF only for APIs **genuinely not relying on browser-auto-sent credentials** after threat-model review, and scope that decision explicitly in security config. Keep CSRF on browser-driven unsafe requests and test login/logout/token rotation flows.

If using `CookieCsrfTokenRepository` for SPAs, understand `HttpOnly`, BREACH/token masking handlers, and how JavaScript obtains the token; never copy an old Spring Security snippet without checking your version.

### 13.4. Do not log secrets while debugging

Observable headers like `Origin`, `Access-Control-Request-Method`, and correlation IDs are far safer to log than full `Cookie`, `Authorization`, or CSRF tokens. In production, log request IDs, methods, normalized paths, statuses, upstream info, latency, and error layer; redact sensitive values.

## 14. Symptom → cause → quick test matrix

| Symptom | Likely error category | Quick test |
| --- | --- | --- |
| Browser reports missing `Access-Control-Allow-Origin`; `curl` returns 200 | CORS response policy | `curl -i -H "Origin: ..."`, inspect headers |
| `OPTIONS` preflight returns 401, no actual `POST` | Spring Security / gateway blocks preflight | Check `http.cors()`, preflight logs, gateway auth |
| Preflight returns 403 "Invalid CORS request" | CORS allowlist/method/header | Compare `Origin`/method/request headers against policy |
| `OPTIONS` 200 yet `POST` 403 | CSRF/authorization likely blocking actual request | Check `CsrfFilter`, token/cookie, and security logs |
| `OPTIONS` 200 yet `GET`/`POST` 404 | Controller route or proxy rewrite | Direct backend request, inspect mappings |
| `GET` 404 when frontend calls `/api/ping`, direct `/api/ping` is 200 | Proxy routing/rewrite | Nginx `proxy_pass` and ingress path rules |
| `GET` 405 | Wrong HTTP method | Check `@GetMapping`/`@PostMapping`, `Allow` header |
| `POST` 415 | Wrong `Content-Type` | Compare against `consumes`, JSON vs. form |
| `GET` 406 | Wrong `Accept`/`produces` | Compare `Accept` and `produces` |
| Browser console says CORS; network response is 502 | Upstream connection/proxy | Gateway error logs, service name, port |
| Browser console says CORS; network is 504 | Upstream timeout | Gateway timeouts and backend/DB duration |
| Browser has no HTTP response, reports TLS | Certificate/mixed content/network | Check HTTPS cert, DNS, browser Security tab |
| CORS credential error when `Allow-Origin=*` | Wildcard invalid with credentials | Use explicit origin and `Allow-Credentials` |
| CORS error only when login expires | Redirect/error response lacks headers | Inspect 302/401/403 and `Location`/headers |
| CORS fails only on staging | Origin/port/proxy policy differs by env | Compare dev/staging `Origin` and Ingress config |
| Two `Allow-Origin` headers | Spring and proxy both emit it | Pick one CORS owner, remove duplicate |
| CORS passes yet API still returns 401 | Missing/expired auth | Check token/session and auth logs |
| CORS passes yet data is wrong | Business logic/DB/serialization | Check controller/service/downstream |
| `POST` from cross-site tab mutates data | Missing CSRF defense or unsafe route | Check CSRF token, `SameSite`, HTTP method |
| CORS error disappears with `mode:"no-cors"` yet JS cannot read JSON | Opaque response | Remove `no-cors`, fix allowlist |

**Never classify solely by status code**; multiple layers can emit the same status. Use request IDs and compare logs across every hop when multiple proxies are present.

## 15. Operations checklist and 10-minute incident workflow

When receiving a "frontend has a CORS bug" report:

1. **Copy the URL, method, origin, and timing** from Network, not just a Console line.
2. Check whether it is a **network/TLS** failure or an actual HTTP response.
3. If `OPTIONS` ran, replay it with `curl` using exact `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
4. Check `Access-Control-Allow-Origin`, methods, headers, credentials, and `Vary`; never slap on wildcards.
5. Send the **actual request** with `curl` to see the real status; handle test cookies/tokens confidentially.
6. For `401/403`, separate authentication, authorization, CSRF, and the CORS processor; preserve needed security controls.
7. For `404/405/415/406`, inspect route, method, `Content-Type`/`Accept`, context path, and controller scanning.
8. For `502/503/504`, inspect proxy/gateway upstream, health, timeouts, DNS, ports, and logs.
9. Call both the backend directly and through the proxy with the same request to find which hop changed it.
10. Apply the fix at **the right layer**, then re-test both allowed and rejected origins, preflight, and actual requests.
11. Confirm browser `fetch` actually reads the response, not just `curl`.
12. Keep regression tests and correlation IDs so the issue does not recur.

**Testing accuracy note:** status/behavior descriptions here apply to the explicitly configured examples. Production can differ depending on `SecurityFilterChain`, middleware, route mappings, and reverse proxies. A request may be blocked at an earlier layer before reaching the layer that would otherwise produce a different status.

## 16. Scenario exercises and answers

### Scenario A — Missing POST, OPTIONS 401

Frontend sends a JSON `POST` with an `Authorization` header. Network shows `OPTIONS` 401 and no `POST`.

**Diagnosis:** preflight was rejected by auth/proxy before the actual request; integrate CORS ahead of authentication or let the gateway handle `OPTIONS` properly. Never attach session cookies to preflight to "bypass" the error.

### Scenario B — OPTIONS 200, POST 403

Preflight has valid `Allow-Origin`, `Allow-Methods`, and `Allow-Headers`; actual `POST` lacks a CSRF token.

**Diagnosis:** CORS passed. With cookie sessions and Spring Security CSRF, 403 is very likely the missing token; check `CsrfFilter` logs. Do not disable CSRF if the app still relies on cookies.

### Scenario C — `curl` backend 200, browser proxy 404

`curl http://localhost:8080/api/ping` returns 200. External Nginx URL `http://localhost:8088/api/ping` returns 404.

**Diagnosis:** check `proxy_pass` trailing slashes, ingress rewrites/path prefixes, and the URI reaching the backend. If the proxy rewrote `/api/ping` to `/ping`, CORS cannot fix the path.

### Scenario D — Console "CORS," Network 502

Proxy returns 502 without CORS headers; Spring logs no request in access logs.

**Diagnosis:** check upstream endpoint/port, service DNS, process health, or gateway connectivity first. The browser's CORS message is merely masking the error response.

### Scenario E — Allowed origin yet credentialed fetch still blocked

Response has `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true`.

**Diagnosis:** combining wildcard with credentials is invalid. Emit `Allow-Origin` with the exact trusted origin and ensure cookie policies match too.

### Scenario F — Switching to `mode:"no-cors"` clears the error yet body is unreadable

**Diagnosis:** the browser returns an opaque response. The call cannot function as a normal JSON API. Fix CORS on the server/proxy or serve same-origin.

### Scenario G — Preflight 200 for a nonexistent URL

`OPTIONS /api/unknown` is approved by the CORS filter, yet actual `POST /api/unknown` returns 404 (if it passes security).

**Diagnosis:** filter-level preflight can run before routing; an `OPTIONS 200` confirms method/header policy, **not that the endpoint exists**.

### Scenario H — 403 when calling from Postman, with no `Origin`

**Diagnosis:** Postman does not enforce browser CORS policies; the failure almost certainly stems from auth/authorization/CSRF/gateway, not browser CORS. Inspect the actual response and logs.

### Scenario I — Spring Boot sees `http` even though user URL is HTTPS

Gateway terminates TLS and sends internal HTTP. Backend builds redirects with wrong host/scheme.

**Diagnosis:** check forwarded headers, `server.forward-headers-strategy`, trust boundary, and gateway rewrites. Do not treat `Origin` or enabling CORS as a fix for redirects.

### Scenario J — SPA and API share a registrable domain on different subdomains

`https://app.example.com` calls `https://api.example.com`.

**Diagnosis:** still cross-origin so CORS is needed, even if same-site under cookie rules. If the cookie is host-only on `app`, the API may not receive it; check cookie domain/path/credentials separately.

## 17. Self-assessment questions

1. **How do CORS and CSRF differ?** CORS governs cross-origin response access from browser scripts; CSRF protects state-changing actions from forged requests leveraging auto-sent credentials.
2. **Does a CORS error prove the server never received the request?** No. The server may have processed it and returned 200/403/500 while the browser blocked JS from reading the response.
3. **Why shouldn't preflight normally need a session cookie?** Browsers send `OPTIONS` to query policy before the actual request; the security chain must process CORS ahead of cookie-based auth.
4. **Does preflight 200 prove a `POST` route exists?** No. A CORS filter can return 200 for a path with no handler; the actual request still gets 404/405.
5. **When `POST` returns 403 while `GET` returns 200, what should you check?** CSRF token, authentication/authorization, method/path, and logs; do not automatically call it a CORS bug.
6. **Can `Access-Control-Allow-Origin: *` be used on credentialed requests?** No. You need an explicit origin and `Access-Control-Allow-Credentials: true`.
7. **Can two origins differ solely by port?** Yes. `localhost:5173` and `localhost:8080` are cross-origin.
8. **Why might `curl` succeed while the browser fails?** `curl` does not enforce browser CORS policies, and may also differ in cookies, TLS trust, or headers.
9. **Does 403 always mean CSRF?** No. The CORS processor, authorization, or WAF/gateway can also return 403.
10. **Is 502 definitely a Spring controller bug?** No. It usually indicates the proxy did not receive a valid upstream response, though logs should confirm.
11. **What can Nginx `proxy_pass http://backend/;` do inside `location /api/`?** It can replace the `/api/` prefix with `/`, breaking backend routes.
12. **Is `Vary: Origin` authorization?** No. It helps caches separate response variants by `Origin`; it grants no permissions.
13. **Does `mode:"no-cors"` let you read JSON APIs?** No. Opaque responses cannot be read normally.
14. **When Spring Security blocks before the controller, is the controller mapping definitely wrong?** No. The request may never have reached `HandlerMapping`; inspect the filter chain.
15. **Can Spring WebFlux use MVC's `HttpSecurity`?** No. WebFlux uses `SecurityWebFilterChain` and reactive CORS counterparts.
16. **When a frontend calls a cross-origin API using session cookies, what must be checked?** CORS allowlist + credentials, cookie policy, auth/CSRF, and proxy/TLS.

## 18. Official references

- [Spring Framework — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): preflight/actual requests, `@CrossOrigin`, global CORS mappings, allowed credentials.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): requirement to process CORS ahead of auth filters; integrating `CorsConfigurationSource` with `SecurityFilterChain`.
- [Spring Security — CSRF protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `CsrfFilter`, token repositories, Spring MVC CSRF endpoints, testing, and BREACH masking.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): CORS in the reactive stack.
- [Spring Boot 3.5 — Embedded web servers and forwarded headers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): TLS termination, proxy headers, config.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): `Origin`, preflight, CORS response headers, and credentials.
- [MDN — CORS errors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors): reasons browsers report CORS errors and how to diagnose them.
- [MDN — Fetch credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): cookies, credentialed requests, and opaque responses.
- [Nginx — ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_pass`, URI rewrites, proxy timeouts, and upstream errors.
- [Spring Framework — Annotated controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): request mappings and method/media-type handling.

**Remember:** a "CORS error" message is a **browser symptom**, not a root-cause diagnosis. Inspect **`OPTIONS` vs. actual request**, **real status/headers**, **Spring Security (CSRF/auth)**, **`HandlerMapping` (path/method)**, and **reverse proxy (rewrites/upstream)** in order. Only after pinpointing the failing layer should you adjust CORS policy, CSRF flow, controller, or proxy—never open wildcards or disable security to mask a bug.