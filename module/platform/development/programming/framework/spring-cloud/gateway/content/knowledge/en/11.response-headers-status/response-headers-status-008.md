# Cookies, Set-Cookie Attributes, and Proxy Impact

## 1. Why do cookies break easily when passing through Spring Cloud Gateway?

A website may call an API through the public address `https://api.example.test/api/auth/login`, while the actual authentication service runs at `http://auth-service:8080/auth/login`. Spring Cloud Gateway receives the request, selects a route via predicates, runs the filter chain, possibly strips a path prefix or alters headers, and forwards the request. When the service returns a response containing **`Set-Cookie`**, the gateway sends that response back to the client.

The problem is that the browser stores cookies based on **the URL the browser sees**, together with the attributes inside `Set-Cookie`. The browser knows nothing about the internal path or hostname the gateway uses to call the backend. If the backend sets a cookie with a `Path` or `Domain` meant for an internal address, the client may fail to store the cookie or fail to send it on the next request, even though the login response returned **200 OK**.

This lesson belongs to the **Headers and Status** chapter of **Spring Cloud Gateway**, focusing on:

- The relationship between the **`Set-Cookie` header in responses** and **`Cookie` in requests**.
- The meaning of `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, `Max-Age`, `Expires`, and special cases.
- The impact of reverse proxies, TLS termination, path rewriting, hosts, redirects, CORS, and multiple cache layers.
- How to configure and verify cookies in Spring Cloud Gateway Server WebFlux without accidentally breaking sessions or weakening authentication.

This knowledge directly relates to building secure API Gateways for microservices: route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux**. Dependency names and YAML namespaces vary across some Spring Cloud versions. Test examples use HTTP on `localhost` with mock cookies; for real login sessions on the Internet, HTTPS and appropriate authentication/authorization mechanisms are required.

## 2. Cookies travel across two different HTTP directions

A cookie is **proposed for storage by the server** via the `Set-Cookie` header in a response. Then **the client decides** whether to store and resend the cookie according to browser rules: domain, path, secure transport, SameSite, expiration, and privacy policies.

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant G as Gateway
    participant A as auth-service
    C->>G: POST /api/auth/login
    Note over G: StripPrefix=1
    G->>A: POST /auth/login
    A-->>G: 200 + Set-Cookie: sid=...; Path=/api/auth
    G-->>C: 200 + Set-Cookie
    Note over C: Validate and store cookie<br/>based on public URL + attributes
    C->>G: GET /api/auth/profile<br/>Cookie: sid=...
    G->>A: GET /auth/profile<br/>Cookie: sid=...
    A-->>G: 200 + data
    G-->>C: 200 + data
~~~

| Header | Direction | Example | Meaning |
| --- | --- | --- | --- |
| **`Set-Cookie`** | Backend → Gateway → client | `Set-Cookie: sid=abc; Path=/api/auth; HttpOnly; Secure; SameSite=Lax` | Instructs the client to store/update a cookie with scope and constraints |
| **`Cookie`** | Client → Gateway → backend | `Cookie: sid=abc` | Client sends cookies eligible for the current request |

**Request cookies do not carry `Path`, `Domain`, `Secure`, or `HttpOnly` attributes.** Those attributes are used by the client when storing and selecting cookies. The backend only receives `name=value` pairs inside the `Cookie` header. If multiple cookies share the same name across different paths/domains, the client may send multiple same-named pairs; the backend cannot infer the original scope solely from the request header.

An HTTP response may contain **multiple independent `Set-Cookie` lines**:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=token-abc; Path=/api/auth; Secure; HttpOnly; SameSite=Lax
Set-Cookie: ui_theme=dark; Path=/; Secure; SameSite=Lax
Content-Type: application/json

{"status":"ok"}
~~~

Never merge two lines into a single `Set-Cookie` line by joining with a comma. Unlike many list-formatted HTTP headers, `Set-Cookie` must remain separate fields; `Expires` can even contain **commas inside HTTP dates**, so splitting/joining with `split(",")` is wrong.

## 3. Set-Cookie attributes you must understand thoroughly

Example response from the public address `https://api.example.test/api/auth/login`:

~~~http
Set-Cookie: sid=opaque-token; Path=/api/auth; Max-Age=1200; Secure; HttpOnly; SameSite=Lax
~~~

| Attribute | Effect | Consequence when passing through a proxy |
| --- | --- | --- |
| **`name=value`** | Cookie name and value | Never store access tokens or readable sensitive information in plain text merely because HTTPS is enabled |
| **`Domain`** | If omitted, the cookie is **host-only**, bound to the public host that returned the response; if set, applies to that domain and matching subdomains | A backend setting `Domain=auth-service.internal` is invalid when the response comes from `api.example.test` |
| **`Path`** | Browser sends the cookie only when the request path falls within the matching scope | A backend setting `Path=/auth` will not match the public URL `/api/auth/profile` |
| **`Secure`** | Sends cookie only over HTTPS (browsers have a special exception for `localhost`) | TLS may terminate at the edge; browsers evaluate HTTPS on the **external URL**, not internal HTTP |
| **`HttpOnly`** | Blocks accessing the cookie via `document.cookie` | Does not stop the browser from automatically sending the cookie on JavaScript requests if cookie/credentials rules permit |
| **`SameSite=Strict`** | Sent only in same-site contexts per browser policy | Suitable when you want maximum restriction against sending cookies from other site contexts |
| **`SameSite=Lax`** | Same-site plus certain safe top-level cross-site navigations | Usually sensible for web login sessions; does not provide complete CSRF protection |
| **`SameSite=None`** | Allows cross-site contexts per browser policy | Modern browsers require pairing with **`Secure`**; also subject to third-party cookie policies |
| **`Max-Age`** | Seconds the cookie remains valid; `0` or negative typically expires the cookie | When both `Max-Age` and `Expires` are present, `Max-Age` takes precedence |
| **`Expires`** | Absolute expiration date/time as an HTTP-date | Requires valid formatting; server/client clock skew can affect how browsers calculate expiration |
| **`Partitioned`** | Stores cookie in storage partitioned by top-level site (CHIPS) in supporting browsers | Requires `Secure`; verify browser support and actual usage context |

### 3.1. Domain: backend host vs. browser host

If the client calls `https://api.example.test/api/auth/login`, the **public host is `api.example.test`**, even when the Gateway forwards to `http://auth-service:8080`.

This is a cookie that is typically valid for the client:

~~~http
Set-Cookie: sid=abc; Path=/api/auth; Secure; HttpOnly; SameSite=Lax
~~~

Because `Domain` is omitted, it is **host-only** on `api.example.test`. Meanwhile:

~~~http
Set-Cookie: sid=abc; Domain=auth-service.internal; Path=/; Secure; HttpOnly
~~~

does not match host `api.example.test`, so the browser rejects it. A server may only set `Domain` to the response's host or a valid parent domain—never an unrelated domain or public suffix like `com`.

When there is no requirement to share cookies across subdomains, **prefer omitting `Domain`** rather than declaring a broad scope like `Domain=example.test`. Cookies are not scoped by **port**; for instance, `localhost:8080` and `localhost:9091` share the same host for domain scoping. Thus, testing two services on two ports of `localhost` does not fully simulate domain changes in production.

### 3.2. Path: browser path vs. gateway-rewritten path

Suppose:

~~~text
Client calls:            /api/auth/login
Gateway StripPrefix=1
Backend receives:        /auth/login

Next client request:     /api/auth/profile
Cookie path must match:  /api/auth/profile
~~~

If the backend returns:

~~~http
Set-Cookie: sid=abc; Path=/auth; Secure; HttpOnly; SameSite=Lax
~~~

then the cookie may be stored by the browser but **will not be sent** when the client calls `/api/auth/profile`: the public path is not under `/auth`. A proper configuration for this example's requirement would be:

~~~http
Set-Cookie: sid=abc; Path=/api/auth; Secure; HttpOnly; SameSite=Lax
~~~

Or `Path=/` if the session genuinely needs to span the entire host, though a broad scope increases the chance of collisions across applications. **`Path` is a cookie-sending rule, not a strong security boundary**; same-host cookies can still be affected by untrusted apps or scripts depending on context.

If `Path` is omitted, browsers use a **default path derived from the public URL of the request that received `Set-Cookie`**, not the internal path seen by the backend. The default value is not necessarily `/`, so session cookies should set their path intentionally.

### 3.3. Secure, TLS termination, and SameSite

Proxies often terminate TLS at the outer edge:

~~~text
Browser -- HTTPS --> Load Balancer -- HTTP --> Gateway -- HTTP --> auth-service
          ^ browser evaluates Secure on this hop
~~~

The backend can still emit `Set-Cookie: ...; Secure` even though it receives internal HTTP: the browser only sees the public response over HTTPS. **`Secure` is still necessary** for login cookies. If a browser actually calls a plain HTTP URL on the Internet, you cannot fake HTTPS by sending `X-Forwarded-Proto: https` to make cookies magically secure.

Public TLS does not protect internal hops by default; if infrastructure requires end-to-end encryption, configure appropriate TLS/mTLS on hops between proxy, gateway, and backend.

`SameSite` classifies by **site**, which is not identical to CORS **origin**. Two origins on different ports can still be same-site; two different hostnames can share a registrable domain, while scheme also matters under schemeful SameSite. When a frontend makes cross-origin API calls via `fetch`, you must still handle CORS/credentials even if the cookie is not classified as a third-party cookie by the browser.

### 3.4. Expiration and deleting cookies

To delete a cookie, return `Set-Cookie` with the matching name, **Path**, and **Domain** of the cookie to remove, and set `Max-Age=0`:

~~~http
Set-Cookie: sid=; Path=/api/auth; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

If login created `Path=/api/auth` while logout only clears `Path=/`, the old cookie can remain because the two scopes do not match. When using multiple same-named cookies on different paths, inspect each cookie entry in the browser. Beyond clearing the client cookie, the authentication system must also invalidate the server-side session/token when security requirements demand it.

## 4. Cookie prefixes and session protection policies

Browsers support prefixes that enforce attribute constraints:

| Cookie name | Key constraints | When to use |
| --- | --- | --- |
| `__Secure-sid` | Must have `Secure` and be set over a valid HTTPS context | Secure sessions where a specific Path or Domain is still needed |
| `__Host-sid` | `Secure`, **`Path=/`**, **no `Domain`**, set over a valid HTTPS context | Host-only cookies, preventing subdomains from sharing/setting scope |
| `__Http-sid` | `Secure` and `HttpOnly` in browsers supporting this prefix | Enforces that the cookie must be set via a `Set-Cookie` response |
| `__Host-Http-sid` | Combines requirements of `__Host-` and `__Http-` | Strict constraint scenarios, subject to browser support |

Example for a session on a public host:

~~~http
Set-Cookie: __Host-sid=opaque; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1200
~~~

Do not copy `__Host-sid` and then set `Path=/api/auth`: prefix-compliant browsers will reject it because it is not `Path=/`. Prefixes also **do not replace authentication**, CSRF protection, XSS defense, server-side token protection, or CORS policies. Constraints depend on browser support for each prefix.

## 5. How does Spring Cloud Gateway affect cookies?

Spring Cloud Gateway Server WebFlux forwards HTTP requests and responses through the selected route. Filters can adjust paths, headers, or status, so distinguish what is **actually modified**.

| Component/mechanism | Effect on cookies |
| --- | --- |
| `Path` predicate, `Host` predicate | Decides **which route** is chosen; predicates themselves do not set cookies |
| `StripPrefix`, `SetPath`, `RewritePath` | Modifies the **request path sent to the backend**; normally does not rewrite `Path=...` in response `Set-Cookie` |
| `AddRequestHeader`, `SetRequestHeader` | Can modify request headers to backend; avoid overwriting or corrupting the user's `Cookie` header |
| `AddResponseHeader` | Appends a response header; works well for diagnostic headers like `X-Gateway-Route` |
| `SetResponseHeader` | **Replaces all values** of the named header; extremely dangerous if the header name is `Set-Cookie` |
| `RemoveResponseHeader` | Removes a response header; setting `RemoveResponseHeader=Set-Cookie` can break login sessions |
| `RewriteResponseHeader` | Replaces response header strings with regex; carelessly editing `Set-Cookie` easily breaks multiple cookies, `Expires`, or attributes |
| `DedupeResponseHeader` | Deduplicates headers, commonly used for CORS; should not be blindly applied to `Set-Cookie` |
| `RedirectTo`, `Location` handling | Can send the client to another URL/host, changing the cookie scope used on the next request |
| `SaveSession` | Requests saving `WebSession` before forwarding, useful with Spring Session; **does not automatically rewrite `Path`/`Domain` of backend-issued cookies** |

According to Spring Cloud Gateway documentation, `SetResponseHeader` **replaces all values** carrying the given name. If the backend returns two different `Set-Cookie` headers, configuring `SetResponseHeader=Set-Cookie, ...` can wipe both and leave only the new value. `DedupeResponseHeader` is built for cases like duplicate CORS headers between gateway and backend; two cookies with the same name but different paths/domains may be two **distinct meaningful cookies**.

Therefore, the easiest option to control is having **the service emit cookies with the public domain/path from the start**. If you must support a legacy backend returning cookies with internal `Path`/`Domain`, design a transformation layer that parses individual cookies properly, preserves independent `Set-Cookie` fields, restricts allowed hosts/paths, and is thoroughly tested—never use a blanket regex to replace all header values.

### 5.1. Response commit: editing Set-Cookie must happen at the right time

In WebFlux, `ServerHttpResponse` lets you add cookies via `response.addCookie(ResponseCookie)` before the response is **committed**. Once headers have been sent to the client, adding/modifying cookies is no longer reliable. If writing a `GlobalFilter` that handles responses, ensure the operation runs at the right stage—registering `beforeCommit(...)` when truly needed—and avoid ad-hoc `block()`/`subscribe()` inside the reactive chain.

For ordinary login flows, setting cookies in the **backend auth service or the Spring Security component managing sessions** is usually clearer than creating cookies in a routing filter.

## 6. Configuring a route to observe cookies through the Gateway

Suppose the gateway runs on `localhost:8080` and the test auth-service runs on `localhost:9091`. The following route only strips the prefix on the way to the backend; it does not alter `Set-Cookie`:

### 6.1. Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: cookie-gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: auth-cookie-lab
              uri: http://localhost:9091
              predicates:
                - Path=/api/auth/**
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Gateway-Lab, auth-cookie-lab
~~~

### 6.2. Gateway Server WebFlux 4.2.x and 4.3.x

For Gateway WebFlux lines using the older prefix for routes, place the same configuration under `spring.cloud.gateway.routes`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: auth-cookie-lab
          uri: http://localhost:9091
          predicates:
            - Path=/api/auth/**
          filters:
            - StripPrefix=1
            - AddResponseHeader=X-Gateway-Lab, auth-cookie-lab
~~~

Use only the **namespace matching your project's version** and WebFlux starter; newer versions typically name the starter `spring-cloud-starter-gateway-server-webflux`, whereas many earlier lines used `spring-cloud-starter-gateway`. The configuration above uses a static URI to isolate cookie issues from service discovery issues. When switching to `lb://auth-service`, add LoadBalancer and an appropriate instance discovery source.

In this lesson, `X-Gateway-Lab` is only a marker that the route ran; it does not prove the browser stored the cookie. You must inspect **`Set-Cookie` in the response** and **`Cookie` in the subsequent request**.

## 7. Practice: mock auth-service issuing and receiving cookies

Create a standalone Spring Boot WebFlux application with dependency `spring-boot-starter-webflux`. The goal is only to test both HTTP directions, **not to implement real authentication**.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091

spring:
  application:
    name: cookie-echo-service
~~~

Entry point class:

~~~java
package demo.cookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieApplication.class, args);
    }
}
~~~

Controller setting the cookie with **`Path=/api/auth` as the public path**, even though the actual backend endpoint is `/auth/login`:

~~~java
package demo.cookie;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/auth")
public class CookieController {

    @PostMapping("/login")
    public Map<String, String> login(ServerHttpResponse response) {
        // Demo cookie; NOT an authenticated session.
        ResponseCookie cookie = ResponseCookie.from(
                        "lab_sid", UUID.randomUUID().toString())
                .path("/api/auth")       // Path visible to the client
                .httpOnly(true)
                .secure(false)            // Only for HTTP localhost lab
                .sameSite("Lax")
                .maxAge(Duration.ofMinutes(10))
                .build();

        response.addCookie(cookie);
        return Map.of("result", "demo-cookie-issued");
    }

    @GetMapping("/profile")
    public Map<String, Object> profile(
            @CookieValue(name = "lab_sid", required = false)
                    String cookie) {
        // Only confirms whether the client sent the cookie; does NOT validate a token.
        return Map.of("cookieReceived", cookie != null);
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(ServerHttpResponse response) {
        ResponseCookie expired = ResponseCookie.from("lab_sid", "")
                .path("/api/auth")       // Must match the Path used at creation
                .httpOnly(true)
                .secure(false)            // Consistent with HTTP lab configuration
                .sameSite("Lax")
                .maxAge(Duration.ZERO)
                .build();

        response.addCookie(expired);
        return ResponseEntity.status(HttpStatus.NO_CONTENT).build();
    }
}
~~~

The code intentionally uses `secure(false)` because the lab runs on `http://localhost`. **Never use that configuration for real sessions on the Internet.** When deploying behind HTTPS, set `secure(true)`, enforce backend session/token policies, enable CSRF protection as needed, and align cookie scope with the public host/path. Never log the value of `lab_sid`.

### 7.1. Starting each process

Run the backend and gateway in **two separate terminals**, each in its respective Maven project directory:

~~~bash
# Backend terminal:
./mvnw spring-boot:run

# Gateway terminal:
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run` or `mvn spring-boot:run`. The example assumes compatible Spring Boot and Spring Cloud BOM dependencies; the outputs below are **expected outputs**, not measurements run on the reader's machine.

### 7.2. Login: observing Set-Cookie and saving a cookie jar

~~~bash
curl -i -X POST "http://localhost:8080/api/auth/login" \
  -c cookie-jar.txt
~~~

The response may look similar to:

~~~http
HTTP/1.1 200 OK
X-Gateway-Lab: auth-cookie-lab
Set-Cookie: lab_sid=<random-value>; Path=/api/auth; Max-Age=600; HttpOnly; SameSite=Lax
Content-Type: application/json

{"result":"demo-cookie-issued"}
~~~

`curl -c cookie-jar.txt` saves the cookie for subsequent requests. Inspect the `Set-Cookie` line specifically; do not rely solely on status 200. In real applications, cookie jar files can contain sensitive session values: **never commit them to Git or share them**.

### 7.3. Profile: verifying the request Cookie reaches the backend

~~~bash
curl -i "http://localhost:8080/api/auth/profile" \
  -b cookie-jar.txt
~~~

Expected response:

~~~http
HTTP/1.1 200 OK
X-Gateway-Lab: auth-cookie-lab
Content-Type: application/json

{"cookieReceived":true}
~~~

This time `curl` sends the `Cookie: lab_sid=...` header on the request to the Gateway; the Gateway forwards to `/auth/profile`, and the controller confirms the cookie arrived. Try calling again **without `-b cookie-jar.txt`** to see `cookieReceived=false`, provided no other cookie is sent.

In this lab, the cookie is selected based on the public path `/api/auth/profile`. If you replace `.path("/api/auth")` with `.path("/auth")` in the login controller and re-run, the cookie may still be saved yet will not be sent on public requests to `/api/auth/profile`. This is the classic failure when the backend is unaware the gateway rewrote the path.

### 7.4. Logout: Max-Age=0 with the same scope

~~~bash
curl -i -X POST "http://localhost:8080/api/auth/logout" \
  -b cookie-jar.txt \
  -c cookie-jar.txt
~~~

Expect **204 No Content** and a `Set-Cookie` header deleting `lab_sid` with `Path=/api/auth; Max-Age=0`. Calling `/api/auth/profile` with the updated cookie jar will return `cookieReceived=false`. This clears the client-side cookie; real authentication applications must also revoke the session/token.

### 7.5. Why can direct backend tests be misleading?

When using the same host `localhost` on two different ports, browsers and cURL do not use **port** to determine cookie scope. A cookie created while calling `localhost:9091` can affect requests to `localhost:8080` if the path matches. Therefore, when testing the backend directly and through the gateway, use separate cookie jars or clear old state to avoid false conclusions.

## 8. Production configuration: Session cookies behind a TLS reverse proxy

Suppose real clients call:

~~~text
https://api.example.test/api/auth/login
        │ TLS
        ▼
Load Balancer / Ingress (TLS termination)
        │ Internal HTTP or HTTPS
        ▼
Spring Cloud Gateway
        │ route /api/auth/** + StripPrefix=1
        ▼
auth-service:8080/auth/login
~~~

If the session is used only on host `api.example.test`, you can choose the cookie:

~~~http
Set-Cookie: __Host-sid=opaque-session-token; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1200
~~~

`__Host-` requires `Path=/` and no `Domain`; if you only want the narrower path `/api/auth`, use another cookie name such as `__Secure-sid` and keep Secure/HTTPS. Never set `Domain=auth-service`, because the internal backend is not the host browsers talk to.

### 8.1. How does the backend determine the HTTPS scheme?

When TLS terminates before the backend, `getURI()` or internal connection info may show `http` even though the client called `https`. If the backend generates redirects or absolute URLs, it needs trusted proxy info about host/scheme, such as `Forwarded` or `X-Forwarded-Proto`/`Host` **validated by the edge proxy**.

However, an `X-Forwarded-Proto: https` header sent by the client itself does not prove the request used TLS. Configure ingress to strip or normalize forwarded headers from the Internet, restrict gateway connection sources, and verify WebFlux/forwarded-header policies for your version. `Secure` is evaluated against the browser's connection to the public URL, not by an arbitrary header.

### 8.2. Should the gateway rewrite Domain/Path?

**Prefer making the backend aware of the public cookie contract** so it returns the right attributes. If a legacy backend always emits:

~~~http
Set-Cookie: sid=abc; Domain=auth.internal; Path=/auth; HttpOnly
~~~

while clients access `https://api.example.test/api/auth/login`, design an explicit translation strategy. Gateway has the regex-based `RewriteResponseHeader` filter, but with `Set-Cookie` extreme care is needed:

- A response may contain **multiple distinct `Set-Cookie` lines**.
- A cookie line can contain `Expires=Wed, 21 Oct ...` with a comma.
- Cookies can have varying `Domain`/`Path`, prefixes, and optional attributes.
- Broad replacements can break sessions or widen cookie scope against policy.

In real systems, use a **proxy-supported explicit cookie-rewriting mechanism** or a custom filter with a compliant parser/serializer, scoped only to controlled routes and cookies. Never use `SetResponseHeader=Set-Cookie,...` to replace all cookie responses. Tests must cover multiple cookies, logout, redirects, and new cookie attributes.

### 8.3. Redirects after login

Login may return `302` or `303` with two headers:

~~~http
HTTP/1.1 303 See Other
Location: /app/home
Set-Cookie: sid=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Clients can store the cookie from the redirect response and send it on the follow-up request if scope allows. When debugging, `curl -i` shows each individual response; `curl -L` follows redirects and can hide intermediate responses unless header display is enabled. If the backend returns `Location: http://auth-service:8080/...`, fix how the backend constructs public URLs or use an appropriate filter to rewrite `Location`. Fixing `Location` **does not automatically fix cookie Domain/Path**.

### 8.4. Multiple proxies adding their own cookies

Load balancers, CDNs, or ingresses sometimes issue cookies for affinity/sticky sessions. These cookies can coexist with login cookies, provided they have distinct names and scopes to avoid collisions. Sticky sessions do not replace authentication; when running multiple backend instances, session state must still be shared or the auth model must allow requests to be served by any instance.

## 9. Cross-origin frontends: CORS, credentials, and SameSite

Suppose a frontend at `https://app.example.test` calls an API at `https://api.example.test` with JavaScript:

~~~javascript
const response = await fetch("https://api.example.test/api/auth/profile", {
  method: "GET",
  credentials: "include"
});
~~~

The two URLs are **cross-origin** because their hostnames differ, even though they may be same-site under SameSite rules. For the browser to allow credentialed requests/responses over CORS, the API needs a matching CORS policy: `Access-Control-Allow-Origin` must match the allowed origin (never `*` with credentials), `Access-Control-Allow-Credentials: true` when required, and preflight handling if the request triggers preflight.

`Set-Cookie` is a response header that browser JavaScript **cannot read directly** via `response.headers.get("set-cookie")`. Inspect it in **DevTools → Network/Storage** or use `curl -i`. Browsers can also ignore `Set-Cookie` in CORS fetch/XHR responses if credentials settings do not match.

When frontend and API are genuinely **cross-site**, `SameSite=Lax` or `Strict` may block cookies across many cross-site requests. `SameSite=None; Secure` is a technical option, though it remains subject to third-party cookie restrictions and each browser's privacy policies. Never use `SameSite=None` just to "fix a login bug" without understanding the context, CSRF, and CORS.

In particular, cookies automatically attached by browsers can open avenues for **CSRF**. `HttpOnly` reduces JavaScript's ability to read cookies, but **does not block state-changing requests**. For cookie-based authentication apps, implement CSRF tokens or CSRF protections fitting your request model and SameSite policy.

## 10. Common symptoms and how to isolate them

| Symptom | Causes to check | Verification steps |
| --- | --- | --- |
| Login returns 200 yet browser does not store cookie | Invalid `Domain`, `Secure` mismatched with URL, `SameSite=None` missing Secure, third-party cookie policy | DevTools Network/Storage and `Set-Cookie` response |
| Browser stores cookie but does not send it on next request | `Path` does not match public URL, wrong Domain, expired cookie, blocked by SameSite/credentials | Compare browser request path with cookie scope |
| Login works directly against backend but fails through gateway | Backend set `Path=/auth` while client calls `/api/auth/...` | Compare `Set-Cookie` headers and paths before/after `StripPrefix` |
| Only one cookie remains after passing through gateway | `SetResponseHeader=Set-Cookie` filter or proxy merging/dropping headers | Check **every** `Set-Cookie` header at backend and client |
| Logout returns 204 yet user stays logged in | Cleared cookie with different `Path`/`Domain`, or server session not invalidated | Compare cookie keys and session store |
| Cookie appears over internal HTTP yet browser rejects it | Browser sees plain HTTP public URL or invalid Secure/SameSite | Check public HTTPS and TLS termination |
| 302 returned but redirects to wrong host | Backend built `Location` from internal hostname or untrusted forwarded headers | Check `Location`, `Host`, `Forwarded`/`X-Forwarded-*` |
| 401/403 despite Cookie header present | Cookie is not a valid session, token expired, backend denied access | Check security logs/traces and server-side session state |
| API returns 429 before login runs | Gateway rate limiter blocked request | Distinguish gateway status from backend response and retry policy |
| Multiple instances give inconsistent session results | In-memory local session, inconsistent affinity, or mismatched signing keys | Check session store/shared keys and selected route instances |

A quick investigation workflow:

1. **Client → Gateway:** check public URL, HTTPS, status, and response `Set-Cookie`.
2. **Gateway → backend:** check route/predicate, rewritten path, and whether response filters alter/remove `Set-Cookie`.
3. **Browser stores cookie:** check Domain, Path, Secure, SameSite, Max-Age, and any rejection reason shown by the browser.
4. **Follow-up request:** check whether the client sends `Cookie` to the public URL; if so, check whether the gateway forwards it to the backend.
5. **Backend/auth:** verify the token/session is valid and authorized; never equate "cookie exists" with "user is authenticated".
6. **Extended factors:** when using `lb://`, retries, circuit breakers, or caching, check target instances, request attempt counts, and any responses modifying cookies.

## 11. Considerations when combining resilience, caching, and observability

**Retries and login:** A request creating a session or refreshing a token has side effects. Retrying without idempotency keys/deduplication logic can create multiple sessions or unexpected `Set-Cookie` responses. Define retry conditions strictly by method, status, body replayability, and business safety. Circuit breakers/fallbacks should likewise never fabricate "fake sessions" when `auth-service` is failing.

**Caching and CDN:** Responses containing session cookies or user data must never be shared across clients through a shared cache. For login or sensitive endpoints, consider `Cache-Control: no-store` and proper CDN/reverse-proxy rules. Never assume the presence of `Set-Cookie` automatically prevents every proxy from caching a response in all cases.

**TLS:** protect the browser → gateway hop and consider HTTPS/mTLS for internal hops per your threat model; avoid putting sensitive raw values inside `Cookie` if transport/logging is not tightly controlled.

**Tracing and logs:** log route ID, method, **public path**, forwarded path, status, latency, trace ID, and cookie diagnostic outcomes at a "present/absent" level when appropriate. Never write `Cookie` or `Set-Cookie` header values containing session tokens into access logs, metric tags, tracing attributes, or exception messages.

**Authorization:** The Gateway can enforce a shared authentication layer, while the backend must still enforce resource-level authorization. Client-supplied `X-User-Id` headers and unverified cookies/signatures are not proof of identity. Path/host/cookie predicates only select routes; they do not replace security policies.

## 12. Pre-deployment checklist

- [ ] Cookies are issued for the **browser's public URL**, with host and return path clearly defined.
- [ ] `Domain` is omitted when subdomain sharing is unneeded; never contains internal service names.
- [ ] Real session cookies use `Secure` over HTTPS, `HttpOnly` when JavaScript does not need to read them, plus appropriate `SameSite` and expiration.
- [ ] `__Host-` prefix is never used with a `Path` other than `/` or with `Domain`.
- [ ] When `StripPrefix`, `RewritePath`, or `SetPath` is present, cookie scope has been aligned with the **external path**.
- [ ] Multi-cookie responses keep **multiple separate `Set-Cookie` lines**; never unintentionally merged, deduped, or overwritten.
- [ ] Logout returns an expired cookie with matching name/Path/Domain and invalidates the server-side session when required.
- [ ] Ingress/CDN performs TLS termination and handles forwarded headers within trust boundaries; spoofed client headers are not trusted.
- [ ] For cross-origin frontends, CORS, credentials, SameSite, browser policies, and CSRF protections are verified.
- [ ] Docs/tests clearly separate HTTP `localhost` labs from HTTPS production configs.
- [ ] Tested login, profile, logout, 302/303, 401, 403, 429, and backend failure/instance failover cases.
- [ ] Sensitive responses are not shared-cached and session tokens are never logged or traced.

## 13. References

1. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Domain, Path, Secure, HttpOnly, SameSite, Max-Age, Expires, Partitioned attributes, and cookie prefixes.
2. [MDN — Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cookie): request Cookie, multiple same-named cookies, and cookie sending scope.
3. [MDN — Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies): principles for minimizing scope and protecting session cookies.
4. [Spring Cloud Gateway Server WebFlux — SetResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setresponseheader-factory.html): filter replacing response header values with the same name.
5. [Spring Cloud Gateway Server WebFlux — DedupeResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/deduperesponseheader-factory.html): removing duplicate headers, commonly used with CORS.
6. [Spring Cloud Gateway Server WebFlux — RewriteResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewriteresponseheader-factory.html): regex-based response header rewriting.
7. [Spring Framework — ResponseCookie](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html): building and issuing cookies on the server.

**Remember:** `Set-Cookie` belongs to the **response** and `Cookie` belongs to **subsequent requests**; the browser determines scope using the **public host/path**, not the backend address behind the Gateway. Set `Domain`/`Path` to match the external URL, protect session cookies with HTTPS/Secure/HttpOnly/SameSite, keep `Set-Cookie` headers independent, and test thoroughly before deploying a proxy in front of microservices.
